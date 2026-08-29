"""切片组合报告：场景模板 × 章节引擎 + 证据链 + 图表 + 抗幻觉"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics, IndustryBenchmark
from app.models.financials import EnterpriseFinancials
from app.schemas.claim import Claim, ClaimTrace, ClaimValue, filter_claims
from app.services import conclusion_store, hallucination_guard, judgment_service, llm_reply
from app.services import assessment, financial_benchmarks, insight_engine, outlook
from app.services.intent_engine import IntentResult
from app.services.report_charts import (
    render_bar_chart_png,
    render_dimension_attribution_png,
    render_funnel_chart_png,
    render_heatmap_chart_png,
    render_line_chart_png,
    render_pie_chart_png,
    render_radar_chart_png,
)
from app.services.chart_payloads import attribution_radar_chart
from app.services.report_html import build_report_html, try_generate_weasyprint_pdf
from app.services.report_templates import (
    PremiumReportLocked,
    build_glossary,
    get_scenario,
    get_scenario_label,
    get_scenario_tier,
    get_scenario_tone,
    is_premium_locked,
    resolve_scenario,
    scope_label,
)
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"

_SAFE_REPORT_ID = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_LEGACY_REPORT = re.compile(r"^ENT\d+_\d{8}_\d{6}\.pdf$", re.I)
_TZ_CN = ZoneInfo("Asia/Shanghai")


def _now_cn() -> datetime:
    return datetime.now(_TZ_CN)


def _new_report_id(prefix: str, key: str) -> str:
    """秒级时间戳 + 短 UUID，避免同秒并发静默覆盖。"""
    safe_key = re.sub(r"[^a-zA-Z0-9_-]", "_", key)[:48] or "general"
    ts = _now_cn().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{safe_key}_{ts}_{uuid.uuid4().hex[:8]}"


def write_report_meta(
    report_id: str,
    *,
    owner: str | None = None,
    kind: str = "slice",
    enterprise_id: str | None = None,
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "report_id": report_id,
        "owner": owner,
        "kind": kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if enterprise_id:
        meta["enterprise_id"] = enterprise_id
    path = REPORTS_DIR / f"{report_id}.meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def read_report_meta(report_id: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / f"{report_id}.meta.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _strip_chart_paths(context: dict[str, Any]) -> dict[str, Any]:
    """剥离图表 PNG 文件路径（渲染后即清理，路径不可复用；图表数据仍在）。"""
    out = dict(context)
    for key in ("radar_chart", "attribution_chart", "benchmark_chart"):
        out.pop(key, None)
    chapters = []
    for ch in out.get("chapters") or []:
        c = dict(ch)
        c.pop("chart_image", None)
        chapters.append(c)
    out["chapters"] = chapters
    return out


def write_report_snapshot(report_id: str, context: dict[str, Any]) -> None:
    """报告结构化快照（与 PDF 同源 context），供 GET /report/:id 结构化回读。

    快照与下载 PDF 同一时点生成，保证「预览/下载/回读」三者一致（快照一致性）。
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{report_id}.context.json"
    payload = _strip_chart_paths(context)
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")


def read_report_snapshot(report_id: str) -> dict[str, Any] | None:
    path = REPORTS_DIR / f"{report_id}.context.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _slice_chapter(idx: int, ch: dict[str, Any]) -> dict[str, Any]:
    """切片报告章节 → 前端结构化章节。结论=声明串联，证据链=声明 trace。"""
    claims = ch.get("claims") or []
    conclusion = "；".join(c.get("claim", "") for c in claims if c.get("claim"))
    evidence: list[str] = []
    for c in claims:
        t = c.get("trace") or {}
        if t.get("table") and t.get("field"):
            evidence.append(f"{t['table']}.{t['field']}")
    return {
        "id": str(idx),
        "title": ch.get("title") or "",
        "description": ch.get("purpose") or "",
        "conclusion": conclusion,
        "evidence_chain": evidence,
        "narration": ch.get("narration") or "",
    }


def _enterprise_chapters(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """企业报告无 chapters 字段，按 overall/dimensions/dupont 合成结构化章节（不伪造）。"""
    chapters: list[dict[str, Any]] = []
    overall = snap.get("overall") or {}
    if overall:
        chapters.append(
            {
                "id": "overall",
                "title": "总体风险评估",
                "description": "",
                "conclusion": overall.get("reason") or "",
                "evidence_chain": [],
                "narration": "",
                "points": overall.get("risk_points") or [],
                "advantages": overall.get("advantages") or [],
                "advice": overall.get("advice") or [],
            }
        )
    for dim in snap.get("dimensions") or []:
        chapters.append(
            {
                "id": dim.get("key") or "dim",
                "title": dim.get("title") or "",
                "description": "",
                "conclusion": dim.get("analysis") or "",
                "evidence_chain": [],
                "narration": "",
                "risk_level": dim.get("risk_level"),
                "metrics": dim.get("metrics") or [],
            }
        )
    if snap.get("dupont"):
        chapters.append(
            {
                "id": "dupont",
                "title": "杜邦分解",
                "description": "ROE = 净利率 × 总资产周转率 × 权益乘数",
                "conclusion": snap["dupont"].get("formula") or "",
                "evidence_chain": [],
                "narration": "",
            }
        )
    return chapters


def build_report_detail(report_id: str, snap: dict[str, Any]) -> dict[str, Any]:
    """快照 context → 前端结构化详情（id/title/summary/kpis/chapters）。

    所有字段均来自与 PDF 同源的快照；无字段即弃权（空串/空表），禁止伪造。
    """
    scenario = snap.get("scenario") or "slice"
    if scenario == "enterprise":
        overall = snap.get("overall") or {}
        score = overall.get("overall_score")
        kpis = [
            {
                "label": "综合评分",
                "value": f"{score:.1f}" if score is not None else "—",
                "unit": "分",
                "source": "assessment.overall_score",
            },
            {
                "label": "风险等级",
                "value": overall.get("risk_level") or "—",
                "unit": "",
                "source": "scoring_layer",
            },
            {
                "label": "财务健康",
                "value": overall.get("health") or "—",
                "unit": "",
                "source": "scoring_layer",
            },
        ]
        summary = overall.get("reason") or ""
        chapters = _enterprise_chapters(snap)
        subtitle = snap.get("scenario_label") or "企业财务分析报告"
    else:
        kpis = [
            {
                "label": k.get("label") or "",
                "value": str(k.get("value", "—")),
                "unit": k.get("unit") or "",
                "source": k.get("source") or "",
                "trace": k.get("trace") or "",
            }
            for k in (snap.get("summary_kpis") or [])
        ]
        summary = snap.get("executive_summary") or ""
        chapters = [_slice_chapter(i, ch) for i, ch in enumerate(snap.get("chapters") or [], start=1)]
        subtitle = snap.get("subtitle") or ""

    return {
        "id": report_id,
        "scenario": scenario,
        "title": snap.get("title") or report_id,
        "subtitle": subtitle,
        "generated_at": snap.get("report_date") or "",
        "summary": summary,
        "kpis": kpis,
        "chapters": chapters,
    }


def can_access_report(report_id: str, user: dict | None, *, auth_required: bool) -> bool:
    """鉴权开启时：仅 owner 或 admin；无 meta 的遗留文件仅 admin。"""
    if not auth_required:
        return True
    if not user:
        return False
    role = user.get("role") or "user"
    if role == "admin":
        return True
    email = user.get("sub") or user.get("email")
    meta = read_report_meta(report_id)
    if not meta or not meta.get("owner"):
        return False
    return bool(email) and meta.get("owner") == email


def cleanup_legacy_reports() -> int:
    """删除旧具名企业报告 PDF（ENT001_*.pdf），保留 slice_* 与 ent_*（个体深度报告）。"""
    if not REPORTS_DIR.exists():
        return 0
    removed = 0
    for f in REPORTS_DIR.glob("*.pdf"):
        name = f.name.lower()
        if _LEGACY_REPORT.match(f.name) or (
            not (name.startswith("slice_") or name.startswith("ent_"))
            and f.suffix.lower() == ".pdf"
        ):
            try:
                f.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("legacy report remove failed %s: %s", f.name, exc)
    return removed


async def _chapter_claims(
    db: AsyncSession,
    session_id: str | None,
    function: str,
    dimension: str,
    industry_l1: str | None = None,
    province: str | None = None,
) -> tuple[list[Claim], dict[str, Any]]:
    if session_id:
        items = await run_blocking(conclusion_store.list_session_conclusions, session_id)
        for item in reversed(items):
            if item.get("function") == function and item.get("dimension") == dimension:
                claims = [
                    Claim.model_validate(c)
                    for c in item.get("claims") or []
                    if not judgment_service.is_synthesis_claim_dict(c)
                ]
                meta = dict(item.get("meta") or {})
                return claims, meta

    intent = IntentResult(
        function=function,
        dimension=dimension,
        intent=f"{function}_{dimension}",
        industry_l1=industry_l1,
        province=province,
    )
    try:
        claims, _, meta = await judgment_service.run_judgment(db, intent, session_id or "report")
    except Exception as exc:
        logger.warning("report chapter judgment unavailable (%s/%s): %s", function, dimension, exc)
        return [], {"function": function, "dimension": dimension, "error": str(exc)}
    return claims, meta


def _claims_to_ctx(claims: list[Claim]) -> list[dict[str, Any]]:
    out = []
    for c in filter_claims(claims):
        if c.confidence == "asserted":
            continue
        out.append(
            {
                "claim": c.claim,
                "confidence": c.confidence,
                "value": c.value.model_dump() if c.value else None,
                "trace": c.trace.model_dump() if c.trace else None,
                "evidence_chain": list(c.evidence_chain or []),
            }
        )
    return out


def _numeric_table_rows(claims: list[dict[str, Any]]) -> list[list[str]]:
    from app.services.metric_registry import RUNTIME_METRIC_LABELS

    rows: list[list[str]] = []
    for c in claims:
        val = c.get("value") or {}
        num = val.get("number")
        if num is None:
            continue
        unit = val.get("unit") or ""
        metric = val.get("metric") or "—"
        label = RUNTIME_METRIC_LABELS.get(metric, metric)
        rows.append([label, f"{num}", unit, (c.get("claim") or "")[:48]])
    return rows


def _sample_note(meta: dict[str, Any]) -> str | None:
    """章节统计子集披露：各章口径不同（如财务仅完整报表子集），须在章节标题下显式标注。"""
    n = meta.get("sample_count")
    if not n:
        return None
    cov = meta.get("financial_coverage")
    if cov is not None and int(cov) != int(n):
        return f"统计子集 {n} 家（其中完整三大报表 {cov} 家）"
    return f"统计子集 {n} 家"


def _chart_subtitle(meta: dict[str, Any]) -> str:
    """图表分母标注：把「占比/均值」的样本基数标到图下方，避免读者无从判断分母。"""
    n = meta.get("sample_count")
    if not n:
        return ""
    cov = meta.get("financial_coverage")
    if cov is not None and int(cov) != int(n):
        return f"样本 N={n} 家（完整三大报表 {cov} 家）"
    return f"样本 N={n} 家"


async def _data_time_window(db: AsyncSession) -> str:
    """业务统计年度窗口（附录披露）。优先取 EnterpriseFinancials.report_year 的 min/max；
    取不到则披露「数据截至最近一次 ETL 快照」。"""
    try:
        rows = list(
            (await db.execute(select(EnterpriseFinancials.report_year))).scalars().all()
        )
    except Exception as exc:
        logger.debug("report_year unavailable: %s", exc)
        rows = []
    years = sorted({y for y in rows if y})
    if len(years) == 1:
        return f"业务数据年度：{years[0]} 年"
    if len(years) >= 2:
        return f"业务数据年度：{years[0]} 年 至 {years[-1]} 年"
    return "数据截至最近一次 ETL 快照（业务年度未知）"


def _build_summary_kpis(chapters: list[dict[str, Any]]) -> list[dict[str, str]]:
    """封面关键指标卡：从各章 meta / claims 聚合。"""
    sample_n = 0
    high_risk_n = 0
    avg_score: float | None = None
    avg_score_label = "综合均分"
    top_industry = "—"
    ind_scores: dict[str, int] = {}

    for ch in chapters:
        meta = ch.get("meta") or {}
        if meta.get("sample_count"):
            sample_n = max(sample_n, int(meta["sample_count"]))
        for key in ("industries", "by_industry"):
            for row in meta.get(key) or []:
                name = row.get("industry_l1")
                if not name:
                    continue
                n = int(row.get("n") or row.get("sample_count") or 1)
                ind_scores[name] = ind_scores.get(name, 0) + n
        if meta.get("low_credit") is not None:
            high_risk_n = max(high_risk_n, int(meta.get("low_credit") or 0))
        if meta.get("flagged_count") is not None:
            high_risk_n = max(high_risk_n, int(meta.get("flagged_count") or 0))
        for c in ch.get("claims") or []:
            val = c.get("value") or {}
            m = val.get("metric")
            n = val.get("number")
            if m in ("avg_score", "overall_score") and n is not None and avg_score is None:
                avg_score = float(n)
                avg_score_label = "综合均分"
            if m == "avg_credit_score" and n is not None and avg_score is None:
                avg_score = float(n)
                avg_score_label = "信用分均分"
            if m == "avg_composite" and n is not None and avg_score is None:
                avg_score = float(n)
                avg_score_label = "综合均分"

    if ind_scores:
        top_industry = max(ind_scores.items(), key=lambda x: x[1])[0]

    if not sample_n:
        for c in chapters[0].get("claims", []) if chapters else []:
            val = (c.get("value") or {})
            if val.get("metric") == "sample_count" and val.get("number"):
                sample_n = int(val["number"])

    kpis = [
        {"label": "样本规模", "value": str(sample_n or "—"), "unit": "家"},
        {"label": "高风险/标记", "value": str(high_risk_n or "—"), "unit": "项"},
        {
            "label": avg_score_label,
            "value": f"{avg_score:.1f}" if avg_score is not None else "—",
            "unit": "分",
        },
        {"label": "关注行业", "value": top_industry, "unit": ""},
    ]
    return kpis


# ── 场景化「主要优势 vs 主要风险」提炼器（L3 场景化，定制化核心）──
# 每个可组合 function 声明「本章哪些数值是优势信号 / 风险信号」，全部从该章 claims/meta 取数，
# 每条挂具体数值；拿不到值即弃权不产出。专项场景只从本报告实际装配的章节提炼，
# 绝不回退全样本六维归因（六维归因只经总览/尽调的 score 章 meta.attribution 天然携带）。
def _financial_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    from app.services.financial_benchmarks import FINANCIAL_RATIOS

    strengths: list[str] = []
    risks: list[str] = []
    for c in claims:
        val = c.get("value") or {}
        metric = val.get("metric")
        num = val.get("number")
        if not metric or num is None:
            continue
        text = c.get("claim") or ""
        cfg = FINANCIAL_RATIOS.get(metric)
        label = (cfg or {}).get("label") or metric
        unit = val.get("unit") or ""
        if "预警" in text:
            risks.append(f"「{label}」{num}{unit}（预警）")
        elif "达标" in text:
            strengths.append(f"「{label}」{num}{unit}（达标）")
    return strengths, risks


# 纳税准时率 ≥95% 视为合规良好（仅作理由层正向锚点，不参与 L1 评级，评级仍由 assessment 统一）
_TAX_ON_TIME_GOOD = 0.95

# 无风险/正常主体占比 ≥80% 才构成「主要优势」；低于此说明样本整体偏险，清净补充不再当作优势（弃权优先）
_CLEAN_RATIO_GOOD = 0.8


def _clean_share_strength(sample: Any, clean: int, label: str) -> str | None:
    """清净主体占比达到阈值才输出为优势锚点；否则返回 None（弃权，不把 5.7% 清净当优势）。"""
    if not sample or not isinstance(clean, int) or clean <= 0:
        return None
    ratio = clean / int(sample)
    if ratio < _CLEAN_RATIO_GOOD:
        return None
    return f"{label} {clean} 家（占比 {ratio * 100:.1f}%）"


def _tax_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    on_time = meta.get("on_time_avg")
    if on_time is not None:
        pct = round(float(on_time) * 100, 1)
        if pct >= _TAX_ON_TIME_GOOD * 100:
            strengths.append(f"纳税准时率均值 {pct}%")
        else:
            risks.append(f"纳税准时率均值 {pct}%（偏低）")
    for label, key in (("欠税主体", "arrears_cnt"), ("税务违法主体", "violation_cnt")):
        n = meta.get(key)
        if n:
            risks.append(f"{label} {int(n)} 家")
    late = meta.get("late_penalty_cnt")
    if late:
        risks.append(f"滞纳/罚款累计 {int(late)} 笔")
    return strengths, risks


def _fraud_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    sample = meta.get("sample_count")
    flagged = meta.get("flagged_count")
    if sample and isinstance(flagged, (int, float)) and int(flagged) < int(sample):
        s = _clean_share_strength(sample, int(sample) - int(flagged), "未触发舞弊标记主体")
        if s:
            strengths.append(s)
    if flagged:
        risks.append(f"触发舞弊标记 {int(flagged)} 家")
    for sig, cnt in (meta.get("signal_counts") or {}).items():
        if cnt is not None:
            risks.append(f"「{sig}」{int(cnt)} 家")
    return strengths, risks


def _authenticity_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    sample = meta.get("sample_count")
    suspicious = meta.get("suspicious_count")
    if sample and isinstance(suspicious, (int, float)) and int(suspicious) < int(sample):
        s = _clean_share_strength(sample, int(sample) - int(suspicious), "经营真实性正常主体")
        if s:
            strengths.append(s)
    if suspicious:
        rate = meta.get("suspicious_rate")
        if rate is not None:
            risks.append(f"交叉偏差可疑 {int(suspicious)} 家（占比 {float(rate) * 100:.1f}%）")
        else:
            risks.append(f"交叉偏差可疑 {int(suspicious)} 家")
    if (meta.get("benford") or {}).get("violation"):
        risks.append("Benford 检验违例（利润累计额首位分布异常）")
    return strengths, risks


def _signal_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    sample = meta.get("sample_count")
    affected = meta.get("unique_affected")
    affected_n = len(affected) if affected else 0
    if sample and affected_n < int(sample):
        s = _clean_share_strength(sample, int(sample) - affected_n, "无风险信号主体")
        if s:
            strengths.append(s)
    for label, key in (
        ("税务违法", "tax_violation"),
        ("营收偏差≥25%", "high_dev"),
        ("信用等级 C/D/M", "low_credit"),
    ):
        n = meta.get(key)
        if n:
            risks.append(f"{label} {int(n)} 家")
    if meta.get("multi_hit_ge2"):
        risks.append(f"同时命中≥2 类风险 {int(meta['multi_hit_ge2'])} 家")
    return strengths, risks


def _score_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    """六维综合评分：仅当本章携带六维归因（总览/尽调的 score 章）时提炼，其余弃权。"""
    strengths: list[str] = []
    risks: list[str] = []
    attr = meta.get("attribution")
    if not attr:
        return strengths, risks
    for d in (attr.get("dimensions") or {}).values():
        score = d.get("score")
        if isinstance(score, (int, float)) and score >= 60:
            strengths.append(f"「{d.get('label', '')}」维度均分 {score:.1f} 分（相对稳健）")
    for f in attr.get("drag_factors") or []:
        item = f.get("item")
        cnt = f.get("count")
        if item and cnt is not None:
            risks.append(f"{item}（{cnt} 家）")
    return strengths, risks


_FUNCTION_SIGNALS: dict[str, Any] = {
    "financial": _financial_signals,
    "tax": _tax_signals,
    "fraud": _fraud_signals,
    "authenticity": _authenticity_signals,
    "signal": _signal_signals,
    "score": _score_signals,
}

# 场景 → 主维度 key：仅对有单一维度锚点的专项场景补「维度主语」（L2 语气层）。
# 综合尽调/总览/画像为六维综合，结论已含「综合均分」，不重复补主语（弃权）。
_SCENARIO_PRIMARY_DIMENSION: dict[str, str] = {
    "financial": "finance",
    "tax": "tax_health",
    "fraud": "invoice",
}


def _scenario_subject_clause(scenario: str | None, attribution: dict[str, Any]) -> str:
    """结论场景主语（L2 语气层）：引用 attribution.dimensions 里已存在的 L1 维度分，
    不重评级、不虚造；无单一维度锚点或维度无数据（0=弃权）时返回空串。"""
    dim_key = _SCENARIO_PRIMARY_DIMENSION.get(scenario or "")
    if not dim_key:
        return ""
    dim = (attribution.get("dimensions") or {}).get(dim_key)
    if not dim or not isinstance(dim.get("score"), (int, float)):
        return ""
    score = float(dim["score"])
    if score <= 0:  # 0=弃权 sentinel：该维度无数据，不补主语
        return ""
    label = dim.get("label") or dim_key
    return f"；{label}维度均分 {score:.1f} 分（{_score_to_risk_level(score)}）"


def _scenario_summary_block(
    chapters: list[dict[str, Any]],
    attribution: dict[str, Any],
    high_risk_ids: set[str],
    scenario: str | None = None,
) -> dict[str, Any]:
    """切片执行摘要「结论前置」块（场景化版）。

    - 结论：综合均分 → 风险等级 + 样本规模（L1 统一评级，场景无关，铁律）；
      专项场景再补一句「维度主语」（L2 语气层，纯表达，不改评级）。
    - 优势/风险：从本报告实际装配的章节按 function 提炼（L3 场景化），每条挂数值；
      专项场景不复读全样本六维归因，杜绝「财务报告列出税务违法」式跑题。
    - 无值弃权：任一 function 无信号即不产出该条，绝不硬凑空分析。

    铁律：结论评级/评分口径不变；此处只决定「理由从哪来、怎么表达」。
    """
    avg_score = attribution.get("avg_score")
    conclusion = ""
    if isinstance(avg_score, (int, float)):
        conclusion = f"综合均分 {avg_score:.1f} 分，风险等级「{_score_to_risk_level(avg_score)}」"
        sample_count = attribution.get("sample_count")
        if sample_count:
            conclusion += f"，样本 {sample_count} 家"
        conclusion += _scenario_subject_clause(scenario, attribution)

    strengths: list[str] = []
    risks: list[str] = []
    for ch in chapters:
        extractor = _FUNCTION_SIGNALS.get(ch.get("function"))
        if not extractor:
            continue
        s, r = extractor(ch.get("claims") or [], ch.get("meta") or {})
        strengths.extend(s)
        risks.extend(r)

    if high_risk_ids:
        risks.append(f"重点关注主体 {len(high_risk_ids)} 家")

    def _dedupe(items: list[str], limit: int) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            if it in seen:
                continue
            seen.add(it)
            out.append(it)
            if len(out) >= limit:
                break
        return out

    return {
        "conclusion": conclusion,
        "strengths": _dedupe(strengths, 3),
        "risks": _dedupe(risks, 4),
    }


# 场景封面 KPI 中「百分比类比率」字段（存 0-1，展示 ×100），对齐 core_metrics 列
_PCT_RATIO_METRICS = {
    "gross_margin", "net_margin", "debt_ratio",
    "vat_burden", "income_tax_burden", "tax_on_time_rate",
}

# fraud 场景封面 KPI：由反欺诈引擎批算（analyze_metrics_batch）聚合
_FRAUD_METRICS = {
    "fraud_signal_count", "suspicious_ratio", "scbm_mismatch_rate", "red_anomaly_ratio",
}


def _slice_ratio_mean(rows: list[Any], field: str) -> float | None:
    """切片比率均值（0=弃权：仅对非 0 样本求均值，无有效样本返回 None）。"""
    vals = [float(getattr(m, field) or 0) for m in rows if float(getattr(m, field) or 0) != 0.0]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _flagged_count(rows: list[Any]) -> int:
    """预警主体计数（税务违法 / 失信 / 被执行 / 低信用），口径对齐 build_signal_claims。"""
    n = 0
    for m in rows:
        if (
            int(getattr(m, "tax_violation_cnt", 0) or 0) > 0
            or bool(getattr(m, "is_dishonesty", False))
            or bool(getattr(m, "is_execution", False))
            or (getattr(m, "credit_level", "") or "") in ("C", "D", "M")
        ):
            n += 1
    return n


def _score_to_risk_level(score: float) -> str:
    """评分 → 风险等级（复用 assessment.RISK_LEVELS 阈值，对齐评分层，避免口径漂移）。"""
    for threshold, label in assessment.RISK_LEVELS:
        if score >= threshold:
            return label
    return "高风险"


def _fmt_ocf(mean_yuan: float) -> str:
    """经营活动现金流均值（元 → 万元字符串），匹配报告「单位：万元」口径。"""
    return _fmt_wan(mean_yuan)


async def _resolve_scenario_kpis(
    db: AsyncSession,
    spec_kpis: list[dict[str, Any]],
    attribution: dict[str, Any],
    industry_l1: str | None = None,
    province: str | None = None,
) -> list[dict[str, Any]]:
    """按场景 KPI 定义从 L0 聚合封面指标卡；无干净来源 → 弃权「—」（不编造）。

    每条返回 {label, value, unit, metric, source, trace}；trace = ``source.metric``，
    供封面「来源」标注与回溯。value 一律字符串（含「—」弃权哨兵）。
    """
    try:
        all_metrics = await assessment._ensure_cache(db)
    except Exception as exc:  # 数据层不可用 → 全部弃权，不阻断报告生成
        logger.debug("scenario kpi cache unavailable: %s", exc)
        all_metrics = []

    # 范围化：行业/地区过滤（报告定制）
    if industry_l1 or province:
        all_metrics = [
            m
            for m in all_metrics
            if (not industry_l1 or m.industry_l1 == industry_l1)
            and (not province or m.province == province)
        ]

    # 经营现金流仅存于 enterprise_financials，按需聚合一次
    fin_ocf: float | None = None
    if any(k.get("metric") == "operating_cf" for k in spec_kpis) and all_metrics:
        try:
            fin_rows = list((await db.execute(select(EnterpriseFinancials))).scalars().all())
        except Exception as exc:
            logger.debug("enterprise financials unavailable for kpi: %s", exc)
            fin_rows = []
        if industry_l1 or province:
            scoped_ids = {m.enterprise_id for m in all_metrics}
            fin_rows = [f for f in fin_rows if getattr(f, "enterprise_id", None) in scoped_ids]
        ocf_vals = [
            float(getattr(f, "operating_cf") or 0)
            for f in fin_rows
            if float(getattr(f, "operating_cf") or 0) != 0.0
        ]
        fin_ocf = (sum(ocf_vals) / len(ocf_vals)) if ocf_vals else None

    # fraud 引擎批算聚合：仅当场景请求 fraud 指标时按需计算一次
    fraud_batch: dict[str, Any] | None = None
    if any(k.get("source") == "fraud" for k in spec_kpis) and all_metrics:
        fraud_rows = [
            (m.enterprise_id, m.display_label or m.enterprise_id, m.industry_l1 or "")
            for m in all_metrics
        ]
        try:
            from app.services import fraud_engine

            fraud_batch = await run_blocking(fraud_engine.analyze_metrics_batch, fraud_rows, max_n=None)
        except Exception as exc:
            logger.debug("fraud cover kpi unavailable: %s", exc)
            fraud_batch = None

    resolved: list[dict[str, Any]] = []
    for kpi in spec_kpis:
        metric = kpi.get("metric")
        source = kpi.get("source") or "—"
        unit = kpi.get("unit") or ""
        value = "—"  # 默认弃权

        if metric == "sample_count":
            value = str(len(all_metrics)) if all_metrics else "—"
        elif metric == "region_count":
            v = len({m.province for m in all_metrics if m.province})
            value = str(v) if v else "—"
        elif metric == "industry_count":
            v = len({m.industry_l1 for m in all_metrics if m.industry_l1})
            value = str(v) if v else "—"
        elif metric == "credit_grade":
            v = len({m.credit_level for m in all_metrics if m.credit_level})
            value = str(v) if v else "—"
        elif metric == "overall_score":
            avg = attribution.get("avg_score")
            value = f"{avg:.1f}" if isinstance(avg, (int, float)) else "—"
        elif metric == "risk_level":
            avg = attribution.get("avg_score")
            value = _score_to_risk_level(avg) if isinstance(avg, (int, float)) else "—"
        elif metric == "flagged_count":
            value = str(_flagged_count(all_metrics)) if all_metrics else "—"
        elif metric == "operating_cf":
            value = _fmt_ocf(fin_ocf) if fin_ocf is not None else "—"
            unit = "万元"
        elif metric in _PCT_RATIO_METRICS:
            v = _slice_ratio_mean(all_metrics, metric)
            value = f"{v * 100:.1f}" if v is not None else "—"
        elif metric == "tax_late_penalty_cnt":
            value = str(sum(int(getattr(m, "tax_late_penalty_cnt", 0) or 0) for m in all_metrics))
        elif metric in _FRAUD_METRICS and fraud_batch and int(fraud_batch.get("sample_count") or 0) > 0:
            sample = int(fraud_batch.get("sample_count") or 0)
            sc = fraud_batch.get("signal_counts") or {}
            if metric == "fraud_signal_count":
                value = str(sum(int(v) for v in sc.values()))
            elif metric == "suspicious_ratio":
                n = int(fraud_batch.get("flagged_count") or 0)
                value = f"{n / sample * 100:.1f}" if sample else "—"
            elif metric == "scbm_mismatch_rate":
                n = int(sc.get("scbm_mismatch", 0) or 0)
                value = f"{n / sample * 100:.1f}" if sample else "—"
            elif metric == "red_anomaly_ratio":
                n = int(sc.get("red_invoice", 0) or 0)
                value = f"{n / sample * 100:.1f}" if sample else "—"
        # benchmark_percentile 等需同业分位基线，当前无干净切片聚合 → 弃权「—」

        resolved.append(
            {
                "label": kpi.get("label"),
                "value": value,
                "unit": unit,
                "metric": metric,
                "source": source,
                "trace": f"{source}.{metric}",
            }
        )
    return resolved


def _fallback_executive_summary(
    summary_kpis: list[dict[str, str]], chapters: list[dict[str, Any]]
) -> str:
    """执行摘要模板兜底：从 KPI 与章节标题拼接，无 LLM 时使用。"""
    kpi_txt = "，".join(f"{k['label']}{k['value']}{k['unit']}" for k in summary_kpis)
    titles = "、".join(ch["title"] for ch in chapters[:5]) or "多维风控分析"
    return (
        f"本报告覆盖「{titles}」等维度，关键指标：{kpi_txt}。"
        "各章节结论均可回溯至表字段，建议结合风险信号优先复核高风险主体。"
    )


def _render_chapter_charts(chapters: list[dict[str, Any]], chart_dir: Path) -> None:
    chart_dir.mkdir(parents=True, exist_ok=True)
    for i, ch in enumerate(chapters):
        chart = ch.get("charts")
        if not chart:
            continue
        path = chart_dir / f"ch_{i + 1}.png"
        title = ch.get("title") or ""
        subtitle = _chart_subtitle(ch.get("meta") or {})
        ctype = chart.get("type")
        if ctype == "line":
            ok = render_line_chart_png(chart, path, title=title, subtitle=subtitle)
        elif ctype == "pie":
            ok = render_pie_chart_png(chart, path, title=title, subtitle=subtitle)
        elif ctype == "radar":
            ok = render_radar_chart_png(chart, path, title=title, subtitle=subtitle)
        elif ctype == "heatmap":
            ok = render_heatmap_chart_png(chart, path, title=title, subtitle=subtitle)
        elif ctype == "funnel":
            ok = render_funnel_chart_png(chart, path, title=title, subtitle=subtitle)
        else:
            ok = render_bar_chart_png(chart, path, title=title, subtitle=subtitle)
        ch["chart_image"] = str(path) if ok else None


async def build_slice_report_context(
    db: AsyncSession,
    *,
    scenario: str = "general",
    session_id: str | None = None,
    query: str | None = None,
    report_id: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
) -> dict[str, Any]:
    key = resolve_scenario(query=query, scenario=scenario)
    if get_scenario_tier(key) == "premium" and is_premium_locked():
        raise PremiumReportLocked(key)
    spec = get_scenario(key)
    return await _build_context_from_spec(
        db,
        key=key,
        spec=spec,
        session_id=session_id,
        report_id=report_id,
        industry_l1=industry_l1,
        province=province,
    )


async def _build_context_from_spec(
    db: AsyncSession,
    *,
    key: str,
    spec: dict[str, Any],
    session_id: str | None = None,
    report_id: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
) -> dict[str, Any]:
    """通用章节装配：给定场景 key + spec dict（固定场景或定制自由组合），产出报告上下文。

    章节循环按 spec["chapters"] 逐个复用 judgment_service 的 8 个 function builder，
    结论/评级始终由 L0/L1 统一给出；此处只决定「结构 + 语气」。
    """
    scope = scope_label(industry_l1, province)
    chapters = []
    chapter_claims: list[list[Claim]] = []

    try:
        attribution = await assessment.get_slice_attribution(db, industry_l1=industry_l1)
    except Exception as exc:
        logger.warning("slice attribution unavailable, degrade to empty: %s", exc)
        attribution = {
            "sample_count": 0,
            "avg_score": 0.0,
            "industry_l1": None,
            "summary": "",
            "dimensions": {},
            "drag_factors": [],
        }

    if session_id:
        syn_claims, syn_meta = await run_blocking(
            judgment_service.build_session_synthesis_claims, session_id
        )
        if syn_claims:
            ctx_syn = _claims_to_ctx(syn_claims)
            chapter_claims.append(syn_claims)
            chapters.append(
                {
                    "title": "综合风控分析",
                    "purpose": "会话内多维度结论汇总",
                    "function": "synthesis",
                    "dimension": "overall",
                    "claims": ctx_syn,
                    "meta": syn_meta,
                    "charts": None,
                    "numeric_rows": _numeric_table_rows(ctx_syn),
                }
            )

    radar_chart = attribution_radar_chart(attribution)
    # 六维雷达·综合画像只前置到「综合尽调」场景；其余专项场景不复读全样本六维归因。
    # （六维归因/雷达的归宿在「总览汇总报告」场景，见 SCENARIOS["overview"]。）
    if key == "due_diligence" and radar_chart and attribution.get("summary"):
        radar_claims = [
            Claim(
                claim=attribution["summary"],
                value=ClaimValue(
                    metric="avg_score",
                    number=attribution.get("avg_score"),
                    unit="分",
                ),
                trace=ClaimTrace(
                    table="assessment",
                    field="overall_score",
                    query_id="Q_report_radar",
                ),
                confidence="computed",
                evidence_chain=[f"sample_count={attribution.get('sample_count')}"],
            )
        ]
        ctx_radar = _claims_to_ctx(radar_claims)
        chapter_claims.append(radar_claims)
        chapters.append(
            {
                "title": "六维雷达 · 综合画像",
                "purpose": "样本六维均分雷达与综合均分",
                "function": "score",
                "dimension": "overall",
                "claims": ctx_radar,
                "meta": {"attribution": attribution},
                "charts": radar_chart,
                "numeric_rows": _numeric_table_rows(ctx_radar),
            }
        )

    for ch in spec["chapters"]:
        claims, meta = await _chapter_claims(
            db, session_id, ch["function"], ch["dimension"],
            industry_l1=industry_l1, province=province,
        )
        safe = []
        for c in claims:
            if c.confidence == "asserted":
                continue
            if c.confidence == "computed" and (not c.trace or not c.trace.table):
                continue
            safe.append(c)
        if not safe:
            logger.debug("skip empty report chapter: %s", ch.get("title"))
            continue
        ctx_claims = _claims_to_ctx(safe)
        chapter_claims.append(safe)
        chapters.append(
            {
                "title": ch["title"],
                "purpose": ch["purpose"],
                "function": ch["function"],
                "dimension": ch["dimension"],
                "claims": ctx_claims,
                "meta": meta,
                "charts": meta.get("charts"),
                "numeric_rows": _numeric_table_rows(ctx_claims),
                "sample_note": _sample_note(meta),
            }
        )

    # 汇总高风险主体（匿名 enterprise_id，明文身份绝不落报告，铁律）：信号 unique_affected +
    # 舞弊 top_flags + 真实性 top_suspicious，去重后作为「重点关注主体清单」附录。
    high_risk_ids: set[str] = set()
    for ch in chapters:
        m = ch.get("meta") or {}
        for eid in m.get("unique_affected") or []:
            if eid:
                high_risk_ids.add(eid)
        for f in m.get("top_flags") or []:
            if isinstance(f, dict) and f.get("enterprise_id"):
                high_risk_ids.add(f["enterprise_id"])
        for s in m.get("top_suspicious") or []:
            if isinstance(s, dict) and s.get("enterprise_id"):
                high_risk_ids.add(s["enterprise_id"])

    time_window = await _data_time_window(db)

    if report_id:
        chart_dir = REPORTS_DIR / "_charts" / report_id
        _render_chapter_charts(chapters, chart_dir)

    # 章节解读：LLM 锚定结论生成（失败则无解读，不影响报告可用性）
    tone = get_scenario_tone(key)
    if llm_reply.is_llm_configured():
        narrations = await asyncio.gather(
            *(
                llm_reply.generate_narration(ch["title"], safe, tone)
                for ch, safe in zip(chapters, chapter_claims)
            )
        )
        for ch, narration in zip(chapters, narrations):
            if narration:
                ch["narration"] = narration

    attribution_chart_path: str | None = None
    if report_id:
        attr_path = REPORTS_DIR / "_charts" / report_id / "attribution.png"
        if render_dimension_attribution_png(attribution, attr_path):
            attribution_chart_path = str(attr_path)

    validation = hallucination_guard.validate_report_chapters(chapters)
    scenario_kpis = await _resolve_scenario_kpis(
        db, list(spec.get("kpis") or []), attribution,
        industry_l1=industry_l1, province=province,
    )
    # 封面/执行摘要统一用场景专属 KPI（metric+source 可回溯）；场景未定义 KPI 时退回通用聚合
    summary_kpis = scenario_kpis or _build_summary_kpis(chapters)
    executive_summary = _fallback_executive_summary(summary_kpis, chapters)
    if llm_reply.is_llm_configured():
        try:
            flat_claims: list[Claim] = [c for cc in chapter_claims for c in cc]
            s = await llm_reply.generate_executive_summary(
                kpis=summary_kpis,
                chapter_titles=[ch["title"] for ch in chapters],
                claims=flat_claims,
                tone=tone,
            )
            if s:
                executive_summary = s
        except Exception as exc:
            logger.warning("executive summary LLM failed: %s", exc)
    summary_block = _scenario_summary_block(chapters, attribution, high_risk_ids, scenario=key)
    return {
        "scenario": key,
        "scenario_label": get_scenario_label(key),
        "tier": get_scenario_tier(key),
        "title": f"{scope} · {spec['title']}" if scope else spec["title"],
        "subtitle": spec.get("subtitle", ""),
        "scope": scope or None,
        "story": spec["story"],
        # 五场景差异化元数据：封面母题/主色 + 数据类侧重 + 场景 KPI 卡定义（L3/L4）
        "cover": spec.get("cover") or {"motif": "compass", "accent": "#003366"},
        "data_focus": list(spec.get("data_focus") or []),
        "scenario_kpis": scenario_kpis,
        "report_date": _now_cn().strftime("%Y年%m月%d日"),
        "chapters": chapters,
        "summary_kpis": summary_kpis,
        "executive_summary": executive_summary,
        "summary_conclusion": summary_block["conclusion"],
        "summary_strengths": summary_block["strengths"],
        "summary_risks": summary_block["risks"],
        "attribution": attribution,
        "attribution_chart": attribution_chart_path,
        "validation": validation,
        "appendix": {
            "data": [
                "core_metrics：匿名税务宽表（PG）",
                "industry_benchmark：行业基准（PG）",
                "syx_invoice / syx_invoice_details：发票明细（MySQL）",
                "syx_tax_finance_profit_year：利润累计额（MySQL，Benford）",
            ],
            "methods": [
                "趋势：revenue_yoy / social_trend 行业聚合",
                "真实性：多源营收偏差 + Benford χ²/MAD",
                "舞弊：scbm 错配、红冲、集中度、序列缺口、pyod IForest",
                "抗幻觉：仅保留 computed/inferred；asserted 丢弃；数字须有 trace",
                "图表：与对话层同源 charts 预渲染 PNG 嵌入 PDF",
                "归因：六维加权贡献 + 高频拖累因素（样本聚合）",
                "渲染：Jinja2 + WeasyPrint（HTML→PDF，FPDF 降级）",
            ],
            "thresholds": financial_benchmarks.FINANCIAL_THRESHOLD_TABLE(),
            "glossary": build_glossary(),
            "time_window": time_window,
            "high_risk_ids": sorted(high_risk_ids),
        },
    }


def _cleanup_chart_dir(report_id: str) -> None:
    chart_dir = REPORTS_DIR / "_charts" / report_id
    if chart_dir.exists():
        shutil.rmtree(chart_dir, ignore_errors=True)


def _generate_slice_pdf_fpdf(context: dict[str, Any], report_id: str, output_path: Path) -> None:
    from fpdf import FPDF

    def _font_path() -> Path | None:
        for p in [
            Path(r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ]:
            if p.exists():
                return p
        return None

    def _text_w(pdf: FPDF) -> float:
        return pdf.w - pdf.l_margin - pdf.r_margin

    def _para(pdf: FPDF, text: str, *, size: int = 11, h: float = 6, align: str = "L") -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=size)
        pdf.multi_cell(_text_w(pdf), h, text or "", align=align)

    def _table(
        pdf: FPDF,
        headers: list[str],
        rows: list[list[str]],
        col_fracs: list[float],
        *,
        size: int = 10,
    ) -> None:
        """用 fpdf2 表格自动换行，替代 cell 截断（避免长文本/术语/规则被切丢）。"""
        tw = _text_w(pdf)
        col_widths = tuple(tw * f for f in col_fracs)
        pdf.set_font(fn, size=size)
        with pdf.table(col_widths=col_widths, first_row_as_headings=False) as tbl:
            for r in [headers] + rows:
                row = tbl.row()
                for cell in r:
                    row.cell(str(cell))

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    font_path = _font_path()
    if font_path:
        pdf.add_font("CN", "", str(font_path))
        fn = "CN"
    else:
        fn = "Helvetica"

    # 封面（严肃正式：品牌 + 标题 + 场景 + 元数据 + 密级，与 HTML 版一致）
    pdf.add_page()
    pdf.start_section("封面")
    pdf.ln(26)
    _para(pdf, "明鉴 · 财税票 · 万景", size=12, h=8, align="C")
    _para(pdf, "风险控制报告", size=10, h=8, align="C")
    pdf.ln(40)
    _para(pdf, context["title"], size=20, h=11, align="C")
    if context.get("subtitle"):
        _para(pdf, context["subtitle"], size=12, h=7, align="C")
    pdf.ln(34)
    tier_txt = "付费定制" if context.get("tier") == "premium" else "通用模板"
    for line in (
        f"报告编号：{report_id}",
        f"报告日期：{context['report_date']}",
        f"报告场景：{context.get('scenario_label', context['scenario'])}",
        f"报告层级：{tier_txt}",
    ):
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=11)
        pdf.cell(_text_w(pdf), 8, line, ln=True, align="C")
    pdf.ln(22)
    _para(pdf, "机密 · 仅限内部使用 · 本报告基于聚合匿名数据生成，不涉及单一主体身份信息", size=9, h=6, align="C")

    # 执行摘要（结论前置：结论 + 主要优势/风险二栏 + 成段理由）
    conclusion = context.get("summary_conclusion")
    strengths = context.get("summary_strengths") or []
    risks = context.get("summary_risks") or []
    exec_summary = context.get("executive_summary")
    if conclusion or strengths or risks or exec_summary:
        pdf.add_page()
        pdf.start_section("执行摘要")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "执行摘要", ln=True)
        kpis = context.get("summary_kpis") or []
        if kpis:
            col_w = _text_w(pdf) / max(len(kpis), 1)
            pdf.set_font(fn, size=10)
            for k in kpis:
                pdf.cell(col_w, 7, k["label"], border=1, align="C")
            pdf.ln()
            for k in kpis:
                pdf.cell(col_w, 10, f"{k['value']}{k['unit']}", border=1, align="C")
            pdf.ln(8)
        if conclusion:
            _para(pdf, conclusion, size=11, h=6)
            pdf.ln(2)

        for head, items in (("主要优势", strengths), ("主要风险", risks)):
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, head, ln=True)
            pdf.set_font(fn, size=10)
            if items:
                for it in items:
                    _para(pdf, f"- {it}", size=10, h=5)
            else:
                _para(pdf, "无数据（弃权）。", size=10, h=5)
            pdf.ln(2)

        if exec_summary:
            _para(pdf, exec_summary, size=11, h=6)
            pdf.ln(3)
        _para(pdf, "本报告为聚合切片，各模块统计子集不同，详见各章节标注。", size=9, h=5)

    # 归因章节（仅综合尽调前置；专项场景不复读全样本六维归因）
    attr = context.get("attribution") or {}
    if context.get("scenario") == "due_diligence" and attr.get("summary"):
        pdf.add_page()
        pdf.start_section("维度归因 · 为什么")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "维度归因 · 为什么", ln=True)
        _para(pdf, attr.get("summary") or "", size=11, h=6)
        pdf.ln(3)

        drag = attr.get("drag_factors") or []
        if drag:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "主要拖累因素", ln=True)
            pdf.set_font(fn, size=10)
            for d in drag[:6]:
                pdf.set_x(pdf.l_margin)
                pdf.cell(_text_w(pdf), 6, f"- {d.get('item', '')}（{d.get('count', 0)} 家）", ln=True)
            pdf.ln(3)

        attr_chart = context.get("attribution_chart")
        if attr_chart and Path(attr_chart).exists():
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "六维加权贡献", ln=True)
            try:
                pdf.image(attr_chart, w=min(_text_w(pdf), 180))
                pdf.ln(4)
            except Exception as exc:
                logger.debug("attribution chart skip: %s", exc)

        dims = attr.get("dimensions") or {}
        if dims:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "维度得分明细", ln=True)
            _table(
                pdf,
                ["维度", "得分", "权重", "加权贡献"],
                [
                    [
                        str(d.get("label", "")),
                        f"{d.get('score', 0):.1f}",
                        f"{float(d.get('weight', 0)) * 100:.0f}%",
                        f"{d.get('net_contribution', 0):.1f}",
                    ]
                    for d in dims.values()
                ],
                [0.4, 0.2, 0.2, 0.2],
            )
            pdf.ln(3)

    # 章节
    for i, ch in enumerate(context["chapters"], 1):
        pdf.add_page()
        pdf.start_section(f"{i}. {ch['title']}")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, f"{i}. {ch['title']}", ln=True)
        _para(pdf, f"功能说明：{ch['purpose']}", size=11, h=6)
        if ch.get("sample_note"):
            _para(pdf, ch["sample_note"], size=10, h=5)
        pdf.ln(2)

        narration = ch.get("narration")
        if narration:
            _para(pdf, narration, size=11, h=6)
            pdf.ln(1)

        chart_path = ch.get("chart_image")
        if chart_path and Path(chart_path).exists():
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "图表", ln=True)
            try:
                pdf.image(chart_path, w=min(_text_w(pdf), 180))
                pdf.ln(4)
            except Exception as exc:
                logger.debug("chart embed skip: %s", exc)

        num_rows = ch.get("numeric_rows") or []
        if num_rows:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "关键数字", ln=True)
            _table(
                pdf,
                ["指标", "数值", "单位", "说明摘要"],
                [[str(c) for c in row] for row in num_rows[:12]],
                [0.22, 0.16, 0.14, 0.48],
            )
            if len(num_rows) > 12:
                _para(pdf, f"… 另有 {len(num_rows) - 12} 项未展示（详见正文结论）。", size=9, h=5)
            pdf.ln(3)

        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=12)
        pdf.cell(_text_w(pdf), 8, "结论", ln=True)
        for c in ch["claims"]:
            prefix = "[据推断] " if c.get("confidence") == "inferred" else ""
            _para(pdf, f"- {prefix}{c.get('claim', '')}", size=11, h=6)
        pdf.ln(2)
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=12)
        pdf.cell(_text_w(pdf), 8, "证据链 / 溯源", ln=True)
        for c in ch["claims"]:
            tr = c.get("trace") or {}
            if not tr:
                continue
            line = (
                f"<- {tr.get('table')}.{tr.get('field')}"
                f"  query={tr.get('query_id')}"
            )
            if tr.get("detail_table"):
                line += f"  detail={tr['detail_table']}"
            _para(pdf, line, size=10, h=5)
            for ev in (c.get("evidence_chain") or [])[:3]:
                _para(pdf, f"   evidence: {ev}", size=10, h=5)

    # 附录
    pdf.add_page()
    pdf.start_section("附录：数据说明")
    pdf.set_x(pdf.l_margin)
    pdf.set_font(fn, size=14)
    pdf.cell(_text_w(pdf), 10, "附录：数据说明", ln=True)
    for s in context["appendix"]["data"]:
        _para(pdf, f"- {s}", size=11, h=6)
    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.set_font(fn, size=14)
    pdf.cell(_text_w(pdf), 10, "附录：方法说明", ln=True)
    for s in context["appendix"]["methods"]:
        _para(pdf, f"- {s}", size=11, h=6)
    pdf.ln(4)

    thresholds = context["appendix"].get("thresholds") or []
    if thresholds:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "附录：四能力判定阈值", ln=True)
        _table(
            pdf,
            ["能力", "指标", "判定规则"],
            [[str(t.get("group", "")), str(t.get("label", "")), str(t.get("rule", ""))] for t in thresholds],
            [0.2, 0.3, 0.5],
        )
    pdf.ln(4)

    time_window = context["appendix"].get("time_window")
    if time_window:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "附录：数据时间窗口", ln=True)
        _para(pdf, time_window, size=11, h=6)
        pdf.ln(4)

    high_risk_ids = context["appendix"].get("high_risk_ids") or []
    if high_risk_ids:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "附录：重点关注主体清单（匿名编号）", ln=True)
        _para(pdf, "以下主体在信号/舞弊/真实性任一维度被标记，建议优先复核（仅匿名编号，不含明文身份）。", size=10, h=5)
        _para(pdf, "、".join(high_risk_ids), size=9, h=5)
        pdf.ln(4)

    glossary = context["appendix"].get("glossary") or []
    if glossary:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "附录：术语词典", ln=True)
        _table(
            pdf,
            ["术语", "含义"],
            [[str(g.get("term", "")), str(g.get("def", ""))] for g in glossary],
            [0.28, 0.72],
        )
    pdf.ln(8)
    _para(
        pdf,
        "本报告由明鉴・财税票・万景自动生成。正文数字均可回溯至表字段；LLM 仅组织语言，不产生新数字。",
        size=10,
        h=5,
    )

    pdf.output(str(output_path))


def _generate_slice_pdf(context: dict[str, Any], report_id: str, output_path: Path) -> None:
    if try_generate_weasyprint_pdf(context, report_id, output_path):
        _cleanup_chart_dir(report_id)
        return
    _generate_slice_pdf_fpdf(context, report_id, output_path)
    _cleanup_chart_dir(report_id)


def _generate_enterprise_pdf_fpdf(context: dict[str, Any], report_id: str, output_path: Path) -> None:
    """个体财务分析报告 FPDF 降级渲染（封面→评级摘要→基本信息→分维度→主要财务数据→免责声明与附录）。"""
    from fpdf import FPDF

    def _font_path() -> Path | None:
        for p in [
            Path(r"C:\Windows\Fonts\msyh.ttc"),
            Path(r"C:\Windows\Fonts\simhei.ttf"),
            Path(r"C:\Windows\Fonts\simsun.ttc"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ]:
            if p.exists():
                return p
        return None

    def _tw(pdf: FPDF) -> float:
        return pdf.w - pdf.l_margin - pdf.r_margin

    def _para(pdf: FPDF, text: str, *, size: int = 11, h: float = 6, align: str = "L") -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=size)
        pdf.multi_cell(_tw(pdf), h, text or "", align=align)

    def _h(pdf: FPDF, text: str, size: int = 14) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=size)
        pdf.cell(_tw(pdf), 10, text, ln=True)

    def _kv(pdf: FPDF, key: str, value: str, key_w: float = 40) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=11)
        pdf.cell(key_w, 8, key, border=1)
        pdf.cell(_tw(pdf) - key_w, 8, str(value), border=1, ln=True)

    def _table(
        pdf: FPDF,
        headers: list[str],
        rows: list[list[str]],
        col_fracs: list[float],
        *,
        size: int = 10,
    ) -> None:
        """用 fpdf2 表格自动换行，替代 cell 截断（长行项目/标准不丢内容）。"""
        tw = _tw(pdf)
        col_widths = tuple(tw * f for f in col_fracs)
        pdf.set_font(fn, size=size)
        with pdf.table(col_widths=col_widths, first_row_as_headings=False) as tbl:
            for r in [headers] + rows:
                row = tbl.row()
                for cell in r:
                    row.cell(str(cell))

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    font_path = _font_path()
    fn = "CN" if font_path else "Helvetica"
    if font_path:
        pdf.add_font("CN", "", str(font_path))

    subject = context.get("subject") or {}
    overall = context.get("overall") or {}

    # 封面
    pdf.add_page()
    pdf.start_section("封面")
    pdf.ln(40)
    _para(pdf, "企业财务分析报告", size=24, h=12, align="C")
    pdf.ln(4)
    _para(pdf, f"样本编号：#{subject.get('short_id', '—')}", size=13, h=7, align="C")
    pdf.ln(2)
    _para(pdf, f"风险等级：{overall.get('risk_level', '—')}", size=13, h=7, align="C")
    pdf.ln(2)
    _para(pdf, f"评级展望：{overall.get('outlook', '—')}", size=13, h=7, align="C")
    pdf.ln(14)
    _para(pdf, f"报告日期：{context.get('report_date', '')}", size=11, h=6, align="C")
    _para(pdf, f"报告编号：{report_id}", size=11, h=6, align="C")

    # 评级摘要（结论前置：等级 + 展望 + 优势/风险 + 成段理由）
    pdf.add_page()
    pdf.start_section("评级摘要")
    _h(pdf, "评级摘要")
    _score = overall.get("overall_score")
    _kv(pdf, "风险等级", overall.get("risk_level", "—"))
    _kv(pdf, "评级展望", overall.get("outlook", "—"))
    _kv(pdf, "综合评分", f"{float(_score):.1f} 分" if _score is not None else "—")
    _kv(pdf, "健康状况", overall.get("health", "—"))
    pdf.ln(3)
    _para(pdf, overall.get("reason") or "", size=11, h=6)

    for title, items in (
        ("主要优势", overall.get("advantages") or []),
        ("主要风险", overall.get("risk_points") or []),
        ("主要建议", overall.get("advice") or []),
    ):
        if not items:
            continue
        pdf.ln(2)
        _h(pdf, title, size=12)
        for it in items:
            _para(pdf, f"- {it}", size=10, h=6)

    # 一、企业基本信息
    pdf.add_page()
    pdf.start_section("一、企业基本信息")
    _h(pdf, "一、企业基本信息")
    _kv(pdf, "样本编号", f"#{subject.get('short_id', '—')}")
    _kv(pdf, "所属行业", f"{subject.get('industry_l1', '—')} / {subject.get('industry_l2', '—')}")
    _kv(pdf, "所属地区", subject.get("province", "—"))
    _kv(pdf, "报告年度", subject.get("report_year", "—"))

    # 二、分维度风险分析（资本结构→偿债→盈利→现金流→营运→成长）
    for i, dim in enumerate(context.get("dimensions") or [], 1):
        pdf.add_page()
        pdf.start_section(f"二.{i} {dim['title']}")
        _h(pdf, f"二.{i} {dim['title']}")
        _kv(pdf, "风险等级", dim.get("risk_level", "—"))
        pdf.ln(2)
        _table(
            pdf,
            ["指标", "数值", "参考标准", "评级"],
            [
                [
                    str(m.get("label", "")),
                    f"{m.get('value', '')}{m.get('unit', '')}",
                    str(m.get("standard", "—")),
                    str(m.get("rating", "—")),
                ]
                for m in dim.get("metrics") or []
            ],
            [0.34, 0.22, 0.24, 0.2],
        )
        pdf.ln(3)
        an = dim.get("analysis") or {}
        for key, title in (
            ("level_review", "风险水平"),
            ("trend", "趋势"),
            ("risks", "风险点"),
            ("advice", "建议"),
        ):
            val = an.get(key)
            if val:
                _para(pdf, f"{title}：{val}", size=10, h=6)

    # 三、主要财务数据
    statements = context.get("statements") or {}
    for idx, st in enumerate(("income", "balance", "cashflow"), 1):
        s = statements.get(st) or {}
        pdf.add_page()
        pdf.start_section(f"三.{idx} {s.get('title', st)}")
        _h(pdf, f"三.{idx} {s.get('title', st)}（单位：万元）")
        pdf.ln(2)
        _table(
            pdf,
            ["项目", "金额（万元）"],
            [[str(row[0]), str(row[1])] for row in s.get("rows") or []],
            [0.6, 0.4],
        )

    # 3.4 杜邦分解（无因子数据 → 弃权不硬凑）
    dupont = context.get("dupont")
    if dupont:
        pdf.add_page()
        pdf.start_section("3.4 杜邦分解")
        _h(pdf, "3.4 杜邦分解")
        _para(pdf, dupont.get("formula") or "", size=11, h=7)
        for f in dupont.get("factors") or []:
            _para(
                pdf,
                f"· {f.get('label', '')}（{f.get('dir', '')}）：{f.get('disp') or '无数据'}",
                size=10, h=6,
            )
        _para(pdf, f"净资产收益率（ROE）：{dupont.get('roe_disp') or '无数据'}", size=10, h=6)
        if dupont.get("complete"):
            factors = dupont.get("factors") or []
            _para(
                pdf,
                f"ROE {dupont.get('roe_disp')} = 净利率 {factors[0]['disp']} × 总资产周转率 {factors[1]['disp']} × 权益乘数 {factors[2]['disp']}。",
                size=10, h=6,
            )
        else:
            _para(pdf, "部分因子无数据/未覆盖（弃权），本期不做完整杜邦分解。", size=10, h=6)

    # 3.5 同业对标（柱状图 PNG；无图则跳过）
    benchmark_chart = context.get("benchmark_chart")
    if benchmark_chart and Path(benchmark_chart).exists():
        pdf.add_page()
        pdf.start_section("3.5 同业对标")
        _h(pdf, "3.5 同业对标（本样本 vs 行业均值，%）")
        try:
            pdf.image(str(benchmark_chart), x=pdf.l_margin, w=_tw(pdf))
        except Exception as exc:  # 图渲染失败不阻断报告输出
            logger.debug("benchmark chart image failed: %s", exc)

    # 四、免责声明与附录
    pdf.add_page()
    pdf.start_section("四、免责声明与附录")
    _h(pdf, "四、免责声明与附录")
    _h(pdf, "数据说明", size=12)
    for s in context["appendix"]["data"]:
        _para(pdf, f"- {s}", size=10, h=6)
    pdf.ln(4)
    _h(pdf, "方法说明", size=12)
    for s in context["appendix"]["methods"]:
        _para(pdf, f"- {s}", size=10, h=6)
    pdf.ln(6)
    _para(
        pdf,
        "本报告由明鉴・财税票・万景自动生成。正文数字均可回溯至表字段；评级由统一阈值决定，无数据处弃权不编造。",
        size=10,
        h=5,
    )

    pdf.output(str(output_path))


def _generate_enterprise_pdf(context: dict[str, Any], report_id: str, output_path: Path) -> None:
    if try_generate_weasyprint_pdf(context, report_id, output_path):
        _cleanup_chart_dir(report_id)
        return
    _generate_enterprise_pdf_fpdf(context, report_id, output_path)
    _cleanup_chart_dir(report_id)


async def preview_slice_report_html(
    db: AsyncSession,
    *,
    scenario: str = "general",
    session_id: str | None = None,
    query: str | None = None,
) -> str:
    """生成报告 HTML 预览（不持久化 PDF）。"""
    key = resolve_scenario(query=query, scenario=scenario)
    preview_id = f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    context = await build_slice_report_context(
        db, scenario=key, session_id=session_id, query=query, report_id=preview_id
    )
    html = build_report_html(context, preview_id)
    _cleanup_chart_dir(preview_id)
    return html


async def generate_slice_report(
    db: AsyncSession,
    *,
    scenario: str = "general",
    session_id: str | None = None,
    query: str | None = None,
    owner: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
) -> tuple[str, Path, dict[str, Any]]:
    cleanup_legacy_reports()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    key = resolve_scenario(query=query, scenario=scenario)
    report_id = _new_report_id("slice", key)
    output_path = REPORTS_DIR / f"{report_id}.pdf"

    context = await build_slice_report_context(
        db,
        scenario=key,
        session_id=session_id,
        query=query,
        report_id=report_id,
        industry_l1=industry_l1,
        province=province,
    )
    if not context.get("chapters") or int(
        (context.get("attribution") or {}).get("sample_count") or 0
    ) <= 0:
        raise ValueError("当前切片无有效样本数据，无法生成报告。请先接入并确认数据。")
    _generate_slice_pdf(context, report_id, output_path)
    write_report_meta(report_id, owner=owner, kind="slice")
    write_report_snapshot(report_id, context)
    return report_id, output_path, context


async def generate_custom_report(
    db: AsyncSession,
    *,
    spec: Any,
    session_id: str | None = None,
    owner: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
) -> tuple[str, Path, dict[str, Any]]:
    """对话式定制报告：把 AI 判定的章节有序子集转成 spec dict，走通用章节装配 + PDF 渲染。

    不经过 resolve_scenario / _canonical，避免 custom→due_diligence 旧映射干扰。
    章节自由组合，但每章结论/评级仍由 L0/L1 统一给出（铁律：AI 只决定结构，不产数字）。
    """
    from app.services.custom_report import spec_to_report_spec

    cleanup_legacy_reports()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_spec = spec_to_report_spec(spec)
    # 前缀用 slice_ 而非 custom_：cleanup_legacy_reports / 报告列表只认 slice_|ent_，
    # 否则定制报告会在下一次生成/列表时被当作遗留文件删除。
    report_id = _new_report_id("slice", "custom")
    output_path = REPORTS_DIR / f"{report_id}.pdf"

    context = await _build_context_from_spec(
        db,
        key="custom",
        spec=report_spec,
        session_id=session_id,
        report_id=report_id,
        industry_l1=industry_l1,
        province=province,
    )
    if not context.get("chapters") or int(
        (context.get("attribution") or {}).get("sample_count") or 0
    ) <= 0:
        raise ValueError("当前切片无有效样本数据，无法生成定制报告。请先接入并确认数据。")
    _generate_slice_pdf(context, report_id, output_path)
    write_report_meta(report_id, owner=owner, kind="slice")
    write_report_snapshot(report_id, context)
    return report_id, output_path, context


# 三大报表行项目（标签 → EnterpriseFinancials 列名），供财务章 numeric_rows
_BALANCE_SHEET = [
    ("资产总计", "total_assets"),
    ("负债合计", "total_liab"),
    ("流动资产合计", "current_assets"),
    ("流动负债合计", "current_liab"),
    ("货币资金", "cash_equiv"),
    ("存货", "inventory"),
    ("应收账款", "accounts_receivable"),
    ("固定资产净额", "fixed_assets"),
    ("短期借款", "short_loan"),
    ("所有者权益合计", "owner_equity"),
    ("未分配利润", "retained_earnings"),
]
_INCOME_STATEMENT = [
    ("营业收入", "revenue"),
    ("营业成本", "cost"),
    ("税金及附加", "tax_surcharge"),
    ("销售费用", "sell_expense"),
    ("管理费用", "admin_expense"),
    ("财务费用", "finance_expense"),
    ("营业利润", "operating_profit"),
    ("利润总额", "total_profit"),
    ("所得税费用", "income_tax"),
    ("净利润", "net_profit"),
]
_CASH_FLOW = [
    ("经营活动现金流量净额", "operating_cf"),
    ("投资活动现金流量净额", "investing_cf"),
    ("筹资活动现金流量净额", "financing_cf"),
]

# 行业基准映射（百分比类比率 → IndustryBenchmark.avg_* 列），供财务章对标柱状图
_BENCH_PCT_RATIOS = [
    ("debt_ratio", "avg_debt_ratio"),
    ("gross_margin", "avg_gross_margin"),
    ("net_margin", "avg_net_margin"),
    ("roe", "avg_roe"),
    ("roa", "avg_roa"),
]


def _threshold_text(cfg: dict[str, Any]) -> str | None:
    """阈值对照文案（百分比 ×100，倍数保留 1 位）。"""
    warn_dir = cfg.get("warn_dir")
    thr = cfg.get("warn_threshold")
    if warn_dir is None or thr is None:
        return None
    op = ">" if warn_dir == "gt" else "<"
    if cfg.get("is_pct"):
        return f"{op}{float(thr) * 100:.0f}%"
    return f"{op}{float(thr):.1f}"


# ── 个体报告 · 对标样张结构（封面→基本信息→总体风险评估→分维度风险分析→主要财务数据→免责声明） ──

_HEALTH_LEVELS: dict[str, tuple[str, str]] = {
    "低风险": ("良好", "#2e7d32"),
    "中低风险": ("良好", "#2e7d32"),
    "中等风险": ("中等", "#f57c00"),
    "中高风险": ("高风险", "#d32f2f"),
    "高风险": ("高风险", "#d32f2f"),
}

# 分维度展示顺序对齐业界「结论前置」骨架：资本结构→偿债→盈利→现金流→营运→成长。
# 其中「资本结构」用 资产负债率 + 资产/负债/权益绝对规模支撑（有数据）；
# 「成长能力」用营收/净利润同比（单期可得趋势）；现金流弱处如实弃权（见 _build_dimension_sections）。
_REPORT_DIMENSIONS: list[dict[str, Any]] = [
    {
        "key": "capital_structure", "title": "资本结构",
        "fields": ["debt_ratio"],
        "amounts": [
            ("资产总计", "total_assets"),
            ("负债合计", "total_liab"),
            ("所有者权益合计", "owner_equity"),
        ],
        "advice": "资产负债率高于 70% 提示杠杆偏高；结合资产、负债与权益绝对规模判断举债结构是否稳健。",
    },
    {
        "key": "solvency", "title": "偿债能力",
        "fields": ["current_ratio", "quick_ratio"],
        "advice": "流动/速动比率低于阈值时，需关注短期偿债压力与再融资能力。",
    },
    {
        "key": "profitability", "title": "盈利能力",
        "fields": ["gross_margin", "net_margin", "roe", "roa"],
        "advice": "关注毛利率与净利率水平；净利率持续偏低时需核查成本结构与定价能力，ROE 为负提示股东回报承压。",
    },
    {
        "key": "cashflow", "title": "现金流",
        "fields": ["operating_cf", "investing_cf", "financing_cf"],
        "advice": "经营活动现金流为负提示自身造血能力不足，需关注回款质量、垫资与对外融资依赖。",
    },
    {
        "key": "operation", "title": "营运能力",
        "fields": ["receivables_turnover", "inventory_turnover", "asset_turnover"],
        "advice": "应收账款与存货周转率偏低提示资金占用与周转效率下降，需加强回款管理与存货去化。",
    },
    {
        "key": "growth", "title": "成长能力",
        "fields": ["revenue_yoy", "profit_yoy"],
        "advice": "营收与净利润同比持续为负提示成长承压；增长与盈利背离时需核查增长质量。",
    },
]

_CASH_FLOW_LABELS: dict[str, str] = {
    "operating_cf": "经营活动现金流量净额",
    "investing_cf": "投资活动现金流量净额",
    "financing_cf": "筹资活动现金流量净额",
}
_CASH_FLOW_STANDARD: dict[str, str] = {"operating_cf": "≥0", "investing_cf": "—", "financing_cf": "—"}


def _fmt_wan(amount: Any) -> str:
    """金额（元）→ 万元字符串，匹配样张「单位：万元」。"""
    try:
        v = float(amount or 0)
    except (TypeError, ValueError):
        return "—"
    return f"{v / 10000:,.2f}"


def _dim_risk_level(warn: int, passed: int, nodata: int, total: int) -> tuple[str, str]:
    """维度风险等级：有预警→高；全达标→低；部分无数据→中（部分覆盖）。"""
    if warn > 0:
        return "高", "#d32f2f"
    if passed == total and nodata == 0:
        return "低", "#2e7d32"
    if nodata > 0:
        return "中", "#f57c00"
    return "低", "#2e7d32"


def _dimension_analysis(
    key: str,
    metrics: list[dict[str, str]],
    warn: int,
    passed: int,
    nodata: int,
    risk: str,
    total: int | None = None,
) -> dict[str, str]:
    """智能分析段（确定性生成，无 AI 味）：当前风险水平评价/指标变化趋势/潜在风险点/简要建议。"""
    total = len(metrics) if total is None else total
    warn_items = [m for m in metrics if m["rating"] == "预警"]
    nodata_items = [m for m in metrics if m["rating"] == "无数据"]
    level_review = (
        f"该维度 {total} 项评级指标中，{warn} 项预警、{passed} 项达标、{nodata} 项无数据，"
        f"整体风险等级「{risk}」。"
    )
    if key == "growth":
        # 营收/净利润同比本身即跨期趋势，直接用数值表达；数据缺失则弃权。
        vals = [f"{m['label']} {m['value']}" for m in metrics if m["rating"] != "无数据"]
        trend = f"成长趋势：{'，'.join(vals)}。" if vals else "成长数据缺失（弃权），暂无法评估趋势。"
    else:
        trend = "本期报告基于单期财务数据，未做跨期趋势比较。"
    if warn_items:
        risks = "；".join(
            f"{m['label']} {m['value']}（参考标准 {m['standard']}）" for m in warn_items
        ) + "。"
    elif nodata_items:
        risks = f"{'、'.join(m['label'] for m in nodata_items)}无数据/未覆盖（弃权），暂无法给出完整结论。"
    else:
        risks = "本期未识别到预警指标。"
    advice = next((s["advice"] for s in _REPORT_DIMENSIONS if s["key"] == key), "")
    return {"level_review": level_review, "trend": trend, "risks": risks, "advice": advice}


def _build_dimension_sections(
    fin: EnterpriseFinancials | None, has_fin: bool
) -> list[dict[str, Any]]:
    dims: list[dict[str, Any]] = []
    for spec in _REPORT_DIMENSIONS:
        key = spec["key"]
        fields = spec["fields"]
        metrics: list[dict[str, str]] = []
        warn = passed = nodata = 0
        rated_total = 0
        for field in fields:
            if key == "cashflow":
                rated_total += 1
                raw = float(getattr(fin, field) or 0) if has_fin else 0.0
                value = _fmt_wan(raw) if has_fin else "—"
                label = _CASH_FLOW_LABELS[field]
                standard = _CASH_FLOW_STANDARD[field]
                if not has_fin or raw == 0.0:
                    rating = "无数据"
                    nodata += 1
                elif field == "operating_cf":
                    if raw < 0:
                        rating = "预警"
                        warn += 1
                    else:
                        rating = "达标"
                        passed += 1
                else:
                    rating = "—"
                metrics.append(
                    {"label": label, "value": value, "unit": "万元", "standard": standard, "rating": rating}
                )
            else:
                cfg = financial_benchmarks.FINANCIAL_RATIOS[field]
                raw = float(getattr(fin, field) or 0) if has_fin else 0.0
                disp = financial_benchmarks.format_financial_ratio(field, raw) if has_fin else "—"
                standard = _threshold_text(cfg) or "—"
                # is_pct 展示值已含 %（format_financial_ratio），unit 置空避免「%%」双写
                unit = cfg["unit"] if not cfg.get("is_pct") else ""
                if cfg.get("warn_dir") is None:
                    # 仅展示项（roa/asset_turnover/profit_yoy），无评级方向，不参与达标/预警计数
                    rating = "无数据" if (not has_fin or raw == 0.0) else "—"
                    metrics.append(
                        {"label": cfg["label"], "value": disp, "unit": unit, "standard": standard, "rating": rating}
                    )
                    continue
                rated_total += 1
                if not has_fin or raw == 0.0:
                    rating = "无数据"
                    nodata += 1
                else:
                    rating = financial_benchmarks.assess_financial_ratio(field, raw)
                    if rating == "预警":
                        warn += 1
                    else:
                        passed += 1
                metrics.append(
                    {"label": cfg["label"], "value": disp, "unit": unit, "standard": standard, "rating": rating}
                )
        # 仅展示金额（资本结构：资产/负债/权益规模，万元），不参与评级计数
        for label, col in spec.get("amounts") or []:
            raw = float(getattr(fin, col) or 0) if has_fin else 0.0
            value = _fmt_wan(raw) if has_fin else "—"
            metrics.append(
                {"label": label, "value": value, "unit": "万元", "standard": "—", "rating": "—"}
            )
        total = rated_total or len(fields)
        risk, color = _dim_risk_level(warn, passed, nodata, total)
        dims.append(
            {
                "key": key,
                "title": spec["title"],
                "risk_level": risk,
                "risk_color": color,
                "metrics": metrics,
                "analysis": _dimension_analysis(key, metrics, warn, passed, nodata, risk, total=total),
            }
        )
    return dims


def _build_statements(fin: EnterpriseFinancials | None, has_fin: bool) -> dict[str, Any]:
    def _rows(items: list[tuple[str, str]]) -> list[list[str]]:
        if not has_fin or fin is None:
            return [[label, "—"] for label, _ in items]
        return [[label, _fmt_wan(getattr(fin, col) or 0)] for label, col in items]

    return {
        "income": {"title": "利润表", "rows": _rows(_INCOME_STATEMENT)},
        "balance": {"title": "资产负债表", "rows": _rows(_BALANCE_SHEET)},
        "cashflow": {"title": "现金流量表", "rows": _rows(_CASH_FLOW)},
    }


def _build_dupont(fin: EnterpriseFinancials | None, has_fin: bool) -> dict[str, Any] | None:
    """杜邦分解（ROE 三因子）；无报表/未覆盖 → None（弃权，不硬凑）。"""
    if not has_fin or fin is None:
        return None
    return financial_benchmarks.dupont_breakdown(
        net_margin=getattr(fin, "net_margin", 0),
        asset_turnover=getattr(fin, "asset_turnover", 0),
        total_assets=getattr(fin, "total_assets", 0),
        owner_equity=getattr(fin, "owner_equity", 0),
        roe=getattr(fin, "roe", 0),
    )


def _build_benchmark_chart(
    fin: EnterpriseFinancials | None, has_fin: bool, bench: IndustryBenchmark | None
) -> dict[str, Any] | None:
    """同业对标柱状图（本样本 vs 行业均值，百分比类比率）；无报表/无基准/全 0 → None。"""
    if not has_fin or fin is None or bench is None:
        return None
    labels, own_vals, bench_vals = [], [], []
    for field, bfield in _BENCH_PCT_RATIOS:
        own = float(getattr(fin, field) or 0)
        if own == 0.0:
            continue
        labels.append(financial_benchmarks.FINANCIAL_RATIOS[field]["label"])
        own_vals.append(own * 100)
        bench_vals.append(float(getattr(bench, bfield) or 0) * 100)
    if not labels:
        return None
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "series": [
                {"name": "行业均值", "values": bench_vals},
                {"name": "本样本", "values": own_vals},
            ],
        },
    }


def _collect_risk_points(
    insights: list[Any],
    signals: list[str],
    fin: EnterpriseFinancials | None = None,
) -> list[str]:
    """风险点采集（数据锚点化）：每条必须挂具体数值，无值的弃权不展示。

    来源优先级：洞察高危/预警（fact_text 自带数值）→ 财务四能力预警比率（挂数值 + 参考标准）
    → 预警信号（枚举标签）。归因负面条目无独立数值，不再进风险点（避免空分析）。
    """
    points: list[str] = []
    for ins in insights:
        if ins.severity in ("高危", "预警"):
            points.append(f"{ins.title}：{ins.fact_text()}")
    if fin is not None:
        for field, cfg in financial_benchmarks.FINANCIAL_RATIOS.items():
            if cfg.get("warn_dir") is None:
                continue  # roa/asset_turnover/profit_yoy 仅展示不评级，不参与风险锚点
            raw = float(getattr(fin, field) or 0)
            if raw != 0 and financial_benchmarks.assess_financial_ratio(field, raw) == "预警":
                std = _threshold_text(cfg) or "—"
                points.append(
                    f"{cfg['label']} {financial_benchmarks.format_financial_ratio(field, raw)}（参考标准 {std}）"
                )
    for s in signals[:3]:
        points.append(f"预警信号：{judgment_service.WARNING_SIGNAL_LABELS.get(s, s)}")
    seen: set[str] = set()
    out: list[str] = []
    for p in points:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out[:6]


# 纳税信用等级里视为「优势」的档位（A/B 为良好；M 新设、C/D 较差，不作为优势挂出）
_GOOD_CREDIT_LEVELS = {"A", "B"}


def _collect_advantages(profile: dict[str, Any], fin: EnterpriseFinancials | None) -> list[str]:
    """优势采集（数据锚点化）：每条必须挂具体数值，无值/非良好档位弃权不展示。

    来源：财务四能力「达标」比率（挂数值）→ 纳税信用等级（A/B 才挂）→ 纳税准时率（≥90% 才挂）。
    """
    adv: list[str] = []
    if fin is not None:
        for field, cfg in financial_benchmarks.FINANCIAL_RATIOS.items():
            if cfg.get("warn_dir") is None:
                continue  # 纯展示项（roa/asset_turnover）无评级方向，不进优势
            raw = float(getattr(fin, field) or 0)
            if raw != 0 and financial_benchmarks.assess_financial_ratio(field, raw) == "达标":
                adv.append(
                    f"{cfg['label']} {financial_benchmarks.format_financial_ratio(field, raw)}，达标"
                )
    credit = str(profile.get("credit_level") or "").strip()
    if credit in _GOOD_CREDIT_LEVELS:
        adv.append(f"纳税信用等级 {credit}")
    on_time = profile.get("tax_on_time_rate")
    if on_time is not None and float(on_time) >= 0.9:
        adv.append(f"纳税准时率 {float(on_time) * 100:.1f}%")
    seen: set[str] = set()
    out: list[str] = []
    for a in adv:
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out[:4] or ["未识别到显著优势项。"]


def _collect_advice(insights: list[Any]) -> list[str]:
    out: list[str] = []
    for ins in insights:
        if ins.advice and ins.advice not in out:
            out.append(ins.advice)
    return out[:4] or ["建议结合同业基准与预警信号，优先复核高风险指标对应的原始凭证。"]


async def build_enterprise_report_context(
    db: AsyncSession, *, enterprise_id: str, report_id: str | None = None
) -> dict[str, Any]:
    """个体财务分析报告上下文（结论前置骨架：封面→评级摘要页→基本信息→分维度风险分析→主要财务数据→免责声明）。

    数字只来自 L0（enterprise_financials / core_metrics）；评级由 financial_benchmarks 统一决定；
    展望由 outlook 规则统一决定；无完整报表时财务维度与报表弃权（不编造），总体风险评估仍基于六维评分与洞察产出。
    """
    from app.services.chart_payloads import enterprise_radar_chart

    profile = await assessment.calculate(db, enterprise_id)
    if not profile:
        raise ValueError("未找到该匿名样本")

    bench = await assessment.peer_benchmark(db, enterprise_id)
    label = profile.get("display_label") or profile.get("enterprise_name")
    short_id = enterprise_id[:8]
    attr = profile.get("attribution") or {}
    signals = profile.get("warning_signals") or []

    # 财务数据（db 为 None 或无报表时弃权，不伪造）
    fin = cm = None
    has_fin = False
    if db is not None:
        fin = await db.get(EnterpriseFinancials, enterprise_id)
        cm = await db.get(CoreMetrics, enterprise_id)
        has_fin = bool(
            fin is not None and cm is not None and getattr(cm, "has_financial_statements", False)
        )

    # 洞察（风险点/建议来源；db 为 None 时跳过）
    insights: list[Any] = []
    if db is not None:
        try:
            insight_metrics, insight_features = await insight_engine.load_insight_inputs(
                db, enterprise_id
            )
            if insight_metrics is not None:
                insights = insight_engine.evaluate_insights(insight_metrics, insight_features)
        except Exception as exc:
            logger.debug("enterprise insights unavailable: %s", exc)

    # ── 评级摘要页（结论前置：风险等级 + 评级展望 + 优势/风险二栏 + 成段理由）──
    risk_level = profile["risk_level"]
    health, health_color = _HEALTH_LEVELS.get(risk_level, ("中等", "#f57c00"))
    outlook_result = outlook.derive_outlook(
        risk_level=risk_level,
        revenue_yoy=getattr(fin, "revenue_yoy", None) if has_fin else None,
        profit_yoy=getattr(fin, "profit_yoy", None) if has_fin else None,
        high_severity_cnt=int(getattr(cm, "high_severity_cnt", 0) or 0) if cm is not None else 0,
    )
    reason = (
        f"综合评分 {profile['overall_score']:.1f} 分，风险等级「{risk_level}」，"
        f"评级展望「{outlook_result['outlook']}」，整体财务健康状况「{health}」。"
    ) + (attr.get("summary") or "")
    risk_points = _collect_risk_points(insights, signals, fin if has_fin else None)
    advantages = _collect_advantages(profile, fin if has_fin else None)
    advice = _collect_advice(insights)

    # ── 分维度风险分析（资本结构→偿债→盈利→现金流→营运→成长） ──
    dimensions = _build_dimension_sections(fin if has_fin else None, has_fin)

    # ── 主要财务数据（利润表/资产负债表/现金流量表，万元） ──
    statements = _build_statements(fin if has_fin else None, has_fin)

    # ── 财务深度分析：杜邦分解 + 同业对标柱状图（无报表/无基准 → 弃权，不硬凑） ──
    dupont = _build_dupont(fin if has_fin else None, has_fin)
    industry_bench: IndustryBenchmark | None = None
    if has_fin and cm is not None and getattr(cm, "industry_l1", None):
        industry_bench = await db.get(IndustryBenchmark, cm.industry_l1)
    benchmark_chart = _build_benchmark_chart(fin if has_fin else None, has_fin, industry_bench)
    benchmark_chart_path: str | None = None
    if benchmark_chart and report_id:
        chart_dir = REPORTS_DIR / "_charts" / report_id
        chart_dir.mkdir(parents=True, exist_ok=True)
        p = chart_dir / "benchmark.png"
        if render_bar_chart_png(benchmark_chart, p, title="同业对标（本样本 vs 行业均值，%）"):
            benchmark_chart_path = str(p)

    # ── 六维风险画像（雷达图，供总体风险评估配图） ──
    radar_chart_path: str | None = None
    if report_id:
        radar = enterprise_radar_chart(profile)
        if radar:
            chart_dir = REPORTS_DIR / "_charts" / report_id
            chart_dir.mkdir(parents=True, exist_ok=True)
            p = chart_dir / "radar.png"
            if render_radar_chart_png(radar, p, title="六维风险画像"):
                radar_chart_path = str(p)

    total_claims = len(risk_points) + sum(len(d["metrics"]) for d in dimensions)
    validation = {"ok": True, "total_claims": total_claims, "unanchored": 0}

    report_year = fin.report_year if has_fin and getattr(fin, "report_year", None) else "—"

    return {
        "scenario": "enterprise",
        "scenario_label": "企业财务分析报告",
        "tier": "general",
        "title": f"企业财务分析报告 · #{short_id}",
        "story": f"针对匿名样本 #{short_id}（{label}）的财务状况深度分析，覆盖资本结构、偿债、盈利、现金流、营运与成长六大维度。",
        "report_date": _now_cn().strftime("%Y年%m月%d日"),
        "subject": {
            "short_id": short_id,
            "label": label,
            "industry_l1": profile.get("industry_l1") or "—",
            "industry_l2": profile.get("industry_l2") or "—",
            "province": profile.get("province") or "—",
            "report_year": report_year,
        },
        "overall": {
            "health": health,
            "health_color": health_color,
            "risk_level": risk_level,
            "outlook": outlook_result["outlook"],
            "outlook_color": outlook_result["color"],
            "overall_score": profile["overall_score"],
            "reason": reason,
            "risk_points": risk_points,
            "advantages": advantages,
            "advice": advice,
            "benchmark_groups": bench.get("groups") if bench else None,
        },
        "dimensions": dimensions,
        "statements": statements,
        "dupont": dupont,
        "benchmark_chart": benchmark_chart_path,
        "radar_chart": radar_chart_path,
        "validation": validation,
        "appendix": {
            "data": [
                "enterprise_financials：企业三大报表宽表（PG）",
                "core_metrics：匿名税务宽表（PG）",
                "industry_benchmark：行业基准（PG）",
                "法律侧仅覆盖税务违法，不含失信/被执行/诉讼（脱敏）",
            ],
            "methods": [
                "六维加权评分：税务健康/真实性/行业地位/法律合规/财务健康/发票健康",
                "财务分维度评级：资本结构/偿债/盈利/现金流/营运/成长，由阈值统一决定（达标/预警/无数据，0=弃权）",
                "同业基准：同行业/同地区/同规模三组 overall_score 百分位",
                "评级展望：负面（高危事件或高风险/中高风险等级）/正面（低风险，或营收与净利润同比均为正）/稳定（其余，趋势缺失弃权）",
                "风险等级：≥80 低风险 / ≥65 中低风险 / ≥50 中等风险 / ≥35 中高风险 / 其余 高风险",
                "脱敏：企业身份以 MD5 哈希展示，无明文企业名",
                "渲染：Jinja2 + WeasyPrint（HTML→PDF，FPDF 降级）",
            ],
        },
    }


async def generate_enterprise_report(
    db: AsyncSession,
    enterprise_id: str,
    *,
    owner: str | None = None,
) -> tuple[str, Path, dict[str, Any]]:
    cleanup_legacy_reports()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_id = _new_report_id("ent", enterprise_id[:8])
    output_path = REPORTS_DIR / f"{report_id}.pdf"

    context = await build_enterprise_report_context(
        db, enterprise_id=enterprise_id, report_id=report_id
    )
    _generate_enterprise_pdf(context, report_id, output_path)
    write_report_meta(report_id, owner=owner, kind="enterprise", enterprise_id=enterprise_id)
    write_report_snapshot(report_id, context)
    return report_id, output_path, context


async def preview_enterprise_report_html(
    db: AsyncSession, *, enterprise_id: str, report_id: str | None = None
) -> str:
    """个体财务分析报告 HTML 预览（与 PDF 同源模板，不持久化 PDF）。"""
    preview_id = report_id or f"preview_ent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    context = await build_enterprise_report_context(
        db, enterprise_id=enterprise_id, report_id=preview_id
    )
    html = build_report_html(context, preview_id)
    _cleanup_chart_dir(preview_id)
    return html


def get_report_path(report_id: str) -> Path | None:
    if not _SAFE_REPORT_ID.match(report_id):
        return None
    path = (REPORTS_DIR / f"{report_id}.pdf").resolve()
    if not str(path).startswith(str(REPORTS_DIR.resolve())):
        return None
    return path if path.exists() else None
