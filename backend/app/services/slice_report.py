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
from app.services.assessment_weights import DIMENSION_LABELS
from app.services.metric_registry import revenue_deviation_warn_label
from app.services.report_html import build_report_html, try_generate_weasyprint_pdf
from app.services.report_templates import (
    CUSTOM_CHAPTER_DIMENSIONS,
    PremiumReportLocked,
    compose_purpose_from_claims,
    compose_story_from_chapters,
    get_scenario,
    get_scenario_label,
    get_scenario_tier,
    get_scenario_tone,
    is_premium_locked,
    radar_dimensions_for_chapters,
    resolve_scenario,
    scope_label,
    business_level,
    zh_industry,
    zh_report_no,
    zh_signal,
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


def _assert_report_renderable(context: dict[str, Any]) -> None:
    """PDF 硬门禁：预校验统一入口（范围/计数/雷达/时序/禁词/权益规则…），不通过拒出报告。"""
    from app.services.report_preflight import assert_renderable_or_raise

    assert_renderable_or_raise(context)


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
                "description": "净资产收益率 = 净利率 × 总资产周转率 × 权益乘数",
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
                "label": "综合经营表现",
                "value": business_level(score) if score is not None else "—",
                "unit": "",
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
        # A.2：详情回读暴露与 PDF 同源的 validation（无则空 dict，禁止伪造 ok）
        "validation": dict(snap.get("validation") or {}),
        "story": snap.get("story") or "",
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
    enterprise_ids: list[str] | None = None,
) -> tuple[list[Claim], dict[str, Any]]:
    # 有切片筛选时禁止复用会话结论缓存（缓存常来自全集对话，会导致税务等场景复现「切片用全集」）。
    use_session_cache = bool(session_id) and not (industry_l1 or province or enterprise_ids)
    if use_session_cache:
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
        enterprises=enterprise_ids or [],
    )
    try:
        claims, _, meta = await judgment_service.run_judgment(db, intent, session_id or "report")
    except Exception as exc:
        logger.warning("report chapter judgment unavailable (%s/%s): %s", function, dimension, exc)
        return [], {"function": function, "dimension": dimension, "error": str(exc)}
    return claims, meta


def _sanitize_slice_context_surfaces(context: dict[str, Any]) -> None:
    """组装出口：用户可见面统一清洗行业代码/内部术语，避免 lexicon 硬拒。"""
    from app.services.report_templates import sanitize_surface_industry_terms

    def _s(text: Any) -> str:
        return sanitize_surface_industry_terms(str(text or ""))

    for key in (
        "title",
        "subtitle",
        "story",
        "executive_summary",
        "summary_conclusion",
        "attribution_brief",
        "scope",
        "scenario_label",
    ):
        if context.get(key):
            context[key] = _s(context.get(key))
    for list_key in ("summary_strengths", "summary_risks"):
        items = context.get(list_key)
        if isinstance(items, list):
            context[list_key] = [_s(x) for x in items]
    highlights = context.get("summary_highlights")
    if isinstance(highlights, dict):
        context["summary_highlights"] = {
            k: [_s(x) for x in (v or [])] if isinstance(v, list) else v
            for k, v in highlights.items()
        }
    cover = context.get("cover_meta")
    if isinstance(cover, dict):
        for k, v in list(cover.items()):
            if isinstance(v, str):
                cover[k] = _s(v)
    attr = context.get("attribution")
    if isinstance(attr, dict) and attr.get("summary"):
        attr["summary"] = _s(attr["summary"])
    for ch in context.get("chapters") or []:
        for k in ("title", "purpose", "narration", "sample_note"):
            if ch.get(k):
                ch[k] = _s(ch.get(k))
        for c in ch.get("claims") or []:
            if isinstance(c, dict) and c.get("claim"):
                c["claim"] = _s(c["claim"])
        rows = ch.get("numeric_rows")
        if isinstance(rows, list):
            ch["numeric_rows"] = [
                [_s(cell) if isinstance(cell, str) else cell for cell in row]
                if isinstance(row, list)
                else row
                for row in rows
            ]
    for kpi in context.get("summary_kpis") or []:
        if isinstance(kpi, dict):
            for part in ("label", "value", "unit"):
                if isinstance(kpi.get(part), str):
                    kpi[part] = _s(kpi[part])


def _claims_to_ctx(claims: list[Claim]) -> list[dict[str, Any]]:
    from app.services.report_templates import sanitize_surface_industry_terms

    out = []
    for c in filter_claims(claims):
        if c.confidence == "asserted":
            continue
        out.append(
            {
                "claim": sanitize_surface_industry_terms(c.claim or ""),
                "confidence": c.confidence,
                "value": c.value.model_dump() if c.value else None,
                "trace": c.trace.model_dump() if c.trace else None,
                "evidence_chain": [
                    sanitize_surface_industry_terms(str(x)) for x in (c.evidence_chain or [])
                ],
            }
        )
    return out


def _numeric_table_rows(claims: list[dict[str, Any]]) -> list[list[str]]:
    """关键数字表：固定 4 列（指标/数值/单位/说明）；空格填【暂无可用数据】，禁止短行错位。"""
    from app.services.metric_registry import format_surface_number, zh_metric_label

    empty = "【暂无可用数据】"
    rows: list[list[str]] = []
    for c in claims:
        val = c.get("value") or {}
        num = val.get("number")
        if num is None:
            continue
        unit = val.get("unit") or ""
        metric = val.get("metric") or ""
        label = zh_metric_label(metric)
        if not label:
            continue  # 弃权：不对外暴露 snake_case / 未知英文键
        claim_text = _strip_bullet_prefix(c.get("claim") or "").strip()
        # 说明摘要：去掉「（样本 n）」类 meta，保留结论句；过短则补一句默认解读
        note = re.sub(r"（样本\s*<?\s*\d+[^）]*）", "", claim_text).strip()
        note = re.sub(r"样本\s*<?\s*\d+[，,、]?\s*(仅供参考[^。]*)?。?", "", note).strip()
        if len(note) < 8:
            note = f"{label}为 {format_surface_number(num, unit, metric=metric)}{unit}，见本章结论。"
        num_disp = format_surface_number(num, unit, metric=metric)
        rows.append(
            [
                label or empty,
                num_disp if str(num_disp).strip() else empty,
                unit if str(unit).strip() else "—",
                note[:120] if note else empty,
            ]
        )
    return rows


def _strip_bullet_prefix(text: str) -> str:
    from app.services.report_templates import strip_bullet_prefix

    return strip_bullet_prefix(text)


def _compact_chapter_narrations(chapters: list[dict[str, Any]]) -> None:
    """正文章节精简：有关键数字表时，去掉与表格重复的信号家数清单句，保留判断+建议。"""
    from app.services.report_templates import sanitize_surface_industry_terms

    for ch in chapters:
        nar = (ch.get("narration") or "").strip()
        if not nar:
            continue
        nar = sanitize_surface_industry_terms(nar)
        if not ch.get("numeric_rows"):
            ch["narration"] = nar
            continue
        parts = [p.strip() for p in re.split(r"(?<=[。！？；])", nar) if p.strip()]
        kept: list[str] = []
        for p in parts:
            # 纯信号清单句（多家点名）→ 丢弃，数字已在表中
            if p.count("家") >= 3 and ("信号" in p or "命中" in p or "分布" in p):
                continue
            if re.search(
                r"(进销错配|集中度|序列缺口|红字发票异常).{0,8}\d+\s*家."
                r"{0,8}(进销错配|集中度|序列缺口|红字发票异常)",
                p,
            ):
                continue
            kept.append(p)
        if not kept:
            # 兜底保留末句（多为建议）
            kept = parts[-1:]
        ch["narration"] = "".join(kept).strip()


def _dedupe_chapter_surface_text(chapters: list[dict[str, Any]]) -> None:
    """去掉子章 narration 中与 sample_note / 同比提示重复的句子（就地改写）。"""
    yoy_hints = (
        "已纳入同比类指标解读",
        "本报告仅提供单年度数据",
        "无可对比的上年历史数据",
        "无法开展同比趋势分析",
        "统计结果仅供参考",
        "样本偏少",
        "样本有限",
    )
    for ch in chapters:
        note = (ch.get("sample_note") or "").strip()
        nar = (ch.get("narration") or "").strip()
        if not nar:
            continue
        if note and note in nar:
            nar = nar.replace(note, "").strip(" ；;，,")
        # 按句去重：样本提示 / 同比提示已在章首或封面出现时，子章不再复读
        parts = [p.strip() for p in re.split(r"(?<=[。！？；])", nar) if p.strip()]
        kept: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            if note and (p == note or p in note or note in p):
                continue
            if any(h in p for h in yoy_hints):
                continue
            seen.add(p)
            kept.append(p)
        ch["narration"] = "".join(kept).strip()


def _chapter_conclusion_lines(ch: dict[str, Any]) -> list[str]:
    from app.services.report_templates import chapter_conclusion_lines

    return chapter_conclusion_lines(ch)


_SMALL_SAMPLE_N = 30  # 低于此阈值：统计结果仅供参考；实现见 scope_contract


def _sample_note(meta: dict[str, Any]) -> str | None:
    """章节统计子集披露：各章口径不同（如财务仅完整报表子集），须在章节标题下显式标注。"""
    from app.services.scope_contract import sample_note

    return sample_note(meta)


def _chart_subtitle(meta: dict[str, Any]) -> str:
    """图表分母标注：把「占比/均值」的样本基数标到图下方，避免读者无从判断分母。"""
    n = meta.get("sample_count")
    if not n:
        return ""
    cov = meta.get("financial_coverage")
    if cov is not None and int(cov) != int(n):
        return f"样本 {n} 家（完整三大报表 {cov} 家）"
    return f"样本 {n} 家"


def _build_summary_kpis(chapters: list[dict[str, Any]]) -> list[dict[str, str]]:
    """封面关键指标卡：从各章 meta / claims 聚合。

    主体计数字段一律单位「家」；含发票舞弊章时第二卡为「舞弊预警主体数」，
    禁止「高风险/标记 + 项」造成「信号条数」歧义。
    """
    sample_n = 0
    high_risk_n = 0
    flagged_from_fraud = False
    avg_score: float | None = None
    top_industry = "—"
    ind_scores: dict[str, int] = {}
    functions = {str(ch.get("function") or "") for ch in chapters}

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
            if ch.get("function") == "fraud":
                flagged_from_fraud = True
        for c in ch.get("claims") or []:
            val = c.get("value") or {}
            m = val.get("metric")
            n = val.get("number")
            if m in ("avg_score", "overall_score", "avg_credit_score") and n is not None and avg_score is None:
                avg_score = float(n)
            if m == "flagged_count" and n is not None:
                high_risk_n = max(high_risk_n, int(n))
                if ch.get("function") == "fraud":
                    flagged_from_fraud = True

    if ind_scores:
        top_industry = max(ind_scores.items(), key=lambda x: x[1])[0]

    if not sample_n:
        for c in chapters[0].get("claims", []) if chapters else []:
            val = (c.get("value") or {})
            if val.get("metric") == "sample_count" and val.get("number"):
                sample_n = int(val["number"])

    # 第二卡：主体家数，禁止「项」
    if flagged_from_fraud or "fraud" in functions:
        risk_label = "舞弊预警主体数"
    else:
        risk_label = "预警主体数"
    risk_value = f"{high_risk_n}" if high_risk_n else "—"
    risk_unit = "家" if high_risk_n else ""

    kpis = [
        {"label": "样本规模", "value": str(sample_n or "—"), "unit": "家" if sample_n else ""},
        {"label": risk_label, "value": risk_value, "unit": risk_unit},
        {
            "label": "综合经营表现",
            "value": business_level(avg_score) if avg_score is not None else "—",
            "unit": "",
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


def _fmt_firm_count(label: str, n: int, sample: Any) -> str:
    """风险主体计数：XX家 / 样本XX家（XX.X%）。"""
    n_i = int(n)
    if sample is None:
        return f"{label} {n_i} 家"
    try:
        sn = int(sample)
    except (TypeError, ValueError):
        return f"{label} {n_i} 家"
    if sn <= 0:
        return f"{label} {n_i} 家"
    pct = min(100.0, round(n_i / sn * 100, 1))
    return f"{label} {n_i} 家 / 样本 {sn} 家（{pct:.1f}%）"


def _attribution_brief(attribution: dict[str, Any] | None) -> str:
    """维度归因精简版：一句 + 拖累条目，避免与执行摘要大段复制。"""
    attr = attribution or {}
    sample = attr.get("sample_count")
    drags = attr.get("drag_factors") or []
    avg = attr.get("avg_score")
    risk = _score_to_risk_level(float(avg)) if isinstance(avg, (int, float)) else "—"
    if not drags:
        return f"群体风险判断「{risk}」。"
    tops = "、".join(str(d.get("item") or "") for d in drags[:3] if d.get("item"))
    if sample and tops:
        return f"群体风险判断「{risk}」；主要拖累：{tops}（见下表家数）。"
    return f"群体风险判断「{risk}」；主要拖累：{tops}。" if tops else f"群体风险判断「{risk}」。"


def _summary_highlight_labels(strengths: list[str], risks: list[str]) -> dict[str, list[str]]:
    """核心要点：只保留指标/信号短名，去掉家数与长叙事。"""

    def _label(text: str) -> str:
        t = str(text or "").strip()
        t = re.split(r"\s+\d+\s*家", t, maxsplit=1)[0]
        t = re.split(r"（", t, maxsplit=1)[0]
        t = t.strip(" ：:·-")
        return t[:32] if t else ""

    out_s = []
    out_r = []
    seen: set[str] = set()
    for raw in strengths:
        lab = _label(raw)
        if lab and lab not in seen:
            seen.add(lab)
            out_s.append(lab)
        if len(out_s) >= 3:
            break
    for raw in risks:
        lab = _label(raw)
        if lab and lab not in seen:
            seen.add(lab)
            out_r.append(lab)
        if len(out_r) >= 4:
            break
    return {"strengths": out_s, "risks": out_r}


def _tax_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    sample = meta.get("sample_count")
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
            risks.append(_fmt_firm_count(label, int(n), sample))
    late = meta.get("late_penalty_cnt")
    if late:
        if sample:
            risks.append(f"滞纳/罚款累计 {int(late)} 笔（样本 {int(sample)} 家）")
        else:
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
        risks.append(_fmt_firm_count("触发舞弊标记", int(flagged), sample))
    for sig, cnt in (meta.get("signal_counts") or {}).items():
        if cnt is not None:
            risks.append(_fmt_firm_count(f"「{zh_signal(sig)}」", int(cnt), sample))
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
        if rate is not None and sample:
            # _fmt_firm_count 已含占比；补充业务口径「超阈占比」时避免双百分比冲突，直接用 rate
            risks.append(
                f"多口径营收不一致 {int(suspicious)} 家 / 样本 {int(sample)} 家"
                f"（{min(100.0, round(float(rate) * 100, 1)):.1f}%）"
            )
        else:
            risks.append(_fmt_firm_count("多口径营收不一致", int(suspicious), sample))
    if (meta.get("benford") or {}).get("violation"):
        risks.append("开票金额首位数字分布偏离自然规律")
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
        (revenue_deviation_warn_label(), "high_dev"),
        ("信用等级 C/D/M", "low_credit"),
    ):
        n = meta.get(key)
        if n:
            risks.append(_fmt_firm_count(label, int(n), sample))
    if meta.get("multi_hit_ge2"):
        risks.append(_fmt_firm_count("同时命中≥2 类风险", int(meta["multi_hit_ge2"]), sample))
    return strengths, risks


def _score_signals(claims: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[str], list[str]]:
    """六维综合评分：仅当本章携带六维归因（总览/尽调的 score 章）时提炼，其余弃权。"""
    strengths: list[str] = []
    risks: list[str] = []
    attr = meta.get("attribution")
    if not attr:
        return strengths, risks
    sample_n = int(meta.get("sample_count") or attr.get("sample_count") or 0)
    for d in (attr.get("dimensions") or {}).values():
        score = d.get("score")
        if isinstance(score, (int, float)) and score >= 60:
            strengths.append(f"「{d.get('label', '')}」维度表现{business_level(score)}")
    for f in attr.get("drag_factors") or []:
        item = f.get("item")
        cnt = f.get("count")
        if item and cnt is not None:
            n = int(cnt)
            if sample_n > 0:
                n = min(n, sample_n)
            risks.append(_fmt_firm_count(str(item), n, sample_n or None))
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
    return f"；{label}维度表现{business_level(score)}"


def _scenario_summary_block(
    chapters: list[dict[str, Any]],
    attribution: dict[str, Any],
    high_risk_ids: set[str],
    scenario: str | None = None,
) -> dict[str, Any]:
    """切片执行摘要「结论前置」块（场景化版）。

    - 结论：综合均分 → 群体风险判断 + 样本规模（L1 统一评级，场景无关，铁律）；
      专项场景再补一句「维度主语」（L2 语气层，纯表达，不改评级）。
    - 优势/风险：从本报告实际装配的章节按 function 提炼（L3 场景化），每条挂数值；
      专项场景不复读全样本六维归因，杜绝「财务报告列出税务违法」式跑题。
    - 无值弃权：任一 function 无信号即不产出该条，绝不硬凑空分析。

    铁律：结论评级/评分口径不变；此处只决定「理由从哪来、怎么表达」。
    """
    avg_score = attribution.get("avg_score")
    conclusion = ""
    if isinstance(avg_score, (int, float)):
        conclusion = f"群体风险判断「{_score_to_risk_level(avg_score)}」"
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

    sample_n = int(attribution.get("sample_count") or 0)
    if high_risk_ids:
        n_hr = len(high_risk_ids)
        risks.append(_fmt_firm_count("重点关注主体", n_hr, sample_n or None))

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
            (m.enterprise_id, m.display_label or m.enterprise_id, m.industry_l1 or "", m.display_name)
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
            value = business_level(avg) if isinstance(avg, (int, float)) else "—"
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
    """执行摘要兜底（结论前置，风控专家口吻）：无 LLM 时用，不硬凑、不编造。"""
    kpi_txt = "，".join(
        f"{k['label']}{k['value']}{k['unit']}"
        for k in summary_kpis
        if k.get("value") not in ("—", "")
    )
    return (
        f"关键指标：{kpi_txt or '—'}。"
        "风险集中处优先核查，先处理拖累最重的维度。"
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


def _is_real_data_claim(c: Claim) -> bool:
    """真实数据 claim（非空占位「暂无数据/样本不足」，非 asserted，非无溯源 computed）。

    空占位 claim 统一以 query_id 后缀 `_empty` 标记（Q_financial_empty / Q_auth_empty / …），
    与真实数据 claim 区分，避免「暂无数据」章节被误判为可用。
    """
    if c.confidence == "asserted":
        return False
    if c.confidence == "computed" and (not c.trace or not c.trace.table):
        return False
    qid = (c.trace.query_id if c.trace else None) or ""
    if qid.endswith("_empty"):
        return False
    return True


async def _chapter_available(
    db: AsyncSession,
    fn: str,
    *,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> tuple[bool, int]:
    """单章可用性：有真实数据 claim（computed/inferred 且可溯源、非空占位）+ 样本量 >0。

    空时不传 enterprise_ids kwarg，兼容测试 monkeypatch 的 _chapter_claims 签名。
    """
    dim = CUSTOM_CHAPTER_DIMENSIONS.get(fn, "overall")
    try:
        if enterprise_ids:
            claims, meta = await _chapter_claims(
                db, None, fn, dim, industry_l1=industry_l1, province=province, enterprise_ids=enterprise_ids
            )
        else:
            claims, meta = await _chapter_claims(
                db, None, fn, dim, industry_l1=industry_l1, province=province
            )
    except Exception as exc:
        logger.debug("chapter availability unavailable (%s): %s", fn, exc)
        return False, 0
    has_real = any(_is_real_data_claim(c) for c in claims)
    sc = meta.get("sample_count")
    # benchmark 等章节 meta 无 sample_count（视作可用）；显式 0（无样本）→ 不可用。
    available = has_real and (sc is None or int(sc) > 0)
    return available, int(sc or 0)


async def _scope_sample_count(
    db: AsyncSession, industry_l1: str | None = None, province: str | None = None
) -> int:
    """当前范围（行业+地区）下企业数，供根因说明（不含指定企业过滤）。"""
    try:
        all_metrics = await assessment._ensure_cache(db)
    except Exception as exc:
        logger.debug("scope sample count unavailable: %s", exc)
        return 0
    return sum(
        1
        for m in all_metrics
        if (not industry_l1 or m.industry_l1 == industry_l1)
        and (not province or m.province == province)
    )


async def validate_custom_report(
    db: AsyncSession,
    *,
    chapters: list[str],
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> dict[str, Any]:
    """定制报告元数据校验：每章可用性 + 样本量 + 范围样本量。

    在 propose 阶段立即调用（而非用户点「确认」时才判空），从源头避免无效提交；
    路由据此拦截（不开放确认按钮）或提示换范围/换章节，而非静默丢章节或报 500。
    """
    chapters_info: dict[str, dict[str, Any]] = {}
    for fn in chapters:
        ok, n = await _chapter_available(
            db, fn, industry_l1=industry_l1, province=province, enterprise_ids=enterprise_ids
        )
        chapters_info[fn] = {"available": ok, "sample_count": n}
    scope_n = await _scope_sample_count(db, industry_l1, province)
    return {
        "chapters": chapters_info,
        "scope_sample_count": scope_n,
        "enterprise_ids": enterprise_ids or [],
    }


async def _wizard_scope_alignment_preview(
    db: AsyncSession,
    *,
    scenario: str,
    industry_l1: str | None = None,
    province: str | None = None,
) -> dict[str, Any]:
    """向导干跑：装配各章 meta.sample_count（无 LLM），对齐 PDF scope_alignment 硬门禁。

    同时扫描章节 claim 文案禁词（行业代码等），对齐 lexicon 硬门禁。
    """
    from app.services.report_templates import (
        sanitize_surface_industry_terms,
        scan_forbidden_in_text,
    )
    from app.services.scope_contract import validate_scope_sample_alignment

    key = resolve_scenario(scenario=scenario)
    spec = get_scenario(key)
    try:
        attribution = await assessment.get_slice_attribution(
            db, industry_l1=industry_l1, enterprise_ids=None
        )
    except Exception as exc:
        logger.debug("wizard scope attr unavailable: %s", exc)
        attribution = {"sample_count": 0}
    scope_n = int(attribution.get("sample_count") or 0)
    chapters: list[dict[str, Any]] = []
    lex_hits: list[str] = []
    # 与 _build_context_from_spec 一致：画像/预警前置雷达章
    if key in ("portrait", "alert", "due_diligence", "overview", "profile") and scope_n > 0:
        chapters.append(
            {
                "title": "六维雷达 · 综合画像",
                "function": "score",
                "meta": {"sample_count": scope_n},
            }
        )
        for bit in (
            sanitize_surface_industry_terms(str(attribution.get("summary") or "")),
            sanitize_surface_industry_terms(scope_label(industry_l1, province) or ""),
        ):
            for hit in scan_forbidden_in_text(bit):
                if hit not in lex_hits:
                    lex_hits.append(hit)
    for ch in spec.get("chapters") or []:
        fn = ch.get("function")
        dim = ch.get("dimension") or "overall"
        if not fn:
            continue
        try:
            claims, meta = await _chapter_claims(
                db,
                None,
                fn,
                dim,
                industry_l1=industry_l1,
                province=province,
                enterprise_ids=None,
            )
        except Exception as exc:
            logger.debug("wizard chapter preview skip %s: %s", fn, exc)
            continue
        chapters.append(
            {
                "title": ch.get("title") or fn,
                "function": fn,
                "meta": meta or {},
            }
        )
        for c in claims or []:
            text = sanitize_surface_industry_terms(getattr(c, "claim", None) or "")
            for hit in scan_forbidden_in_text(text):
                if hit not in lex_hits:
                    lex_hits.append(hit)
    align = validate_scope_sample_alignment(
        chapters,
        scope_sample_count=scope_n,
        industry_l1=industry_l1,
        province=province,
    )
    align["lexicon_hits"] = lex_hits
    if lex_hits:
        align["ok"] = False
        align["lexicon_ok"] = False
    else:
        align["lexicon_ok"] = True
    return align


async def validate_wizard_report(
    db: AsyncSession,
    *,
    scenario: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_id: str | None = None,
) -> dict[str, Any]:
    """固定场景向导预校验：生成前判定是否有样本/可溯源章，避免「点生成才发现空」。

    - 指定企业：企业须在 live 样本中；
    - 切片场景：范围样本量 >0 且场景至少一章有真实 claim。
    """
    if enterprise_id:
        try:
            all_metrics = await assessment._ensure_cache(db)
        except Exception as exc:
            logger.debug("wizard enterprise cache unavailable: %s", exc)
            all_metrics = []
        found = next((m for m in all_metrics if m.enterprise_id == enterprise_id), None)
        if not found:
            return {
                "ok": False,
                "mode": "enterprise",
                "scenario": "enterprise",
                "scope_sample_count": 0,
                "available_chapter_count": 0,
                "chapters": {},
                "reason": "未找到该企业样本，请换一家或先完成数据接入。",
            }
        return {
            "ok": True,
            "mode": "enterprise",
            "scenario": "enterprise",
            "scope_sample_count": 1,
            "available_chapter_count": 1,
            "chapters": {},
            "reason": "",
            "enterprise_name": found.display_name or found.display_label or enterprise_id[:8],
        }

    key = resolve_scenario(scenario=scenario)
    if get_scenario_tier(key) == "premium" and is_premium_locked():
        return {
            "ok": False,
            "mode": "slice",
            "scenario": key,
            "scope_sample_count": 0,
            "available_chapter_count": 0,
            "chapters": {},
            "reason": "该场景为付费定制，当前未开放。",
        }
    spec = get_scenario(key)
    # 场景模板表面文案禁词预检（避免「向导通过、生成因 lexicon 硬拒」矛盾）
    from app.services.report_templates import scan_forbidden_in_text

    surface_bits = [
        str(spec.get("title") or ""),
        str(spec.get("subtitle") or ""),
        str(get_scenario_label(key) or ""),
    ]
    for ch in spec.get("chapters") or []:
        surface_bits.append(str(ch.get("title") or ""))
        surface_bits.append(str(ch.get("purpose") or ""))
    lex_hits: list[str] = []
    for bit in surface_bits:
        for hit in scan_forbidden_in_text(bit):
            if hit not in lex_hits:
                lex_hits.append(hit)
    if lex_hits:
        return {
            "ok": False,
            "mode": "slice",
            "scenario": key,
            "scope_sample_count": 0,
            "available_chapter_count": 0,
            "chapters": {},
            "reason": (
                f"场景文案含内部术语（{'、'.join(lex_hits[:5])}），"
                "请联系管理员修正模板后再生成。"
            ),
            "lexicon_hits": lex_hits,
        }

    fns = [ch.get("function") for ch in (spec.get("chapters") or []) if ch.get("function")]
    meta = await validate_custom_report(
        db, chapters=fns, industry_l1=industry_l1, province=province
    )
    chapters_info = meta.get("chapters") or {}
    available = sum(1 for info in chapters_info.values() if info.get("available"))
    scope_n = int(meta.get("scope_sample_count") or 0)
    ok = scope_n > 0 and available > 0
    reason = ""
    if not ok:
        reason = await custom_report_block_reason(
            db,
            industry_l1=industry_l1,
            province=province,
            enterprise_ids=None,
            scope_sample_count=scope_n,
        )
        if available <= 0 and scope_n > 0:
            reason = f"{reason}当前场景暂无可用章节结论，请换场景或范围。"
    # 有筛选时：干跑章节 meta.sample_count，对齐 PDF 硬门禁 scope_alignment（避免向导过、生成拒）
    scope_preview: dict[str, Any] | None = None
    if ok and (industry_l1 or province):
        scope_preview = await _wizard_scope_alignment_preview(
            db,
            scenario=key,
            industry_l1=industry_l1,
            province=province,
        )
        if scope_preview and not scope_preview.get("ok"):
            ok = False
            mism = scope_preview.get("mismatches") or []
            lex_h = scope_preview.get("lexicon_hits") or []
            if lex_h:
                reason = (
                    f"报告文案含内部术语（{'、'.join(lex_h[:5])}），"
                    "生成会被禁词门禁拒绝，请换范围或联系管理员。"
                )
            else:
                detail = "；".join(
                    f"{m.get('chapter')} {m.get('chapter_n')}家≠范围{m.get('scope_n')}家"
                    for m in mism[:3]
                )
                reason = f"范围样本对齐失败：{detail or '章节统计子集与筛选不一致'}。"
    return {
        "ok": ok,
        "mode": "slice",
        "scenario": key,
        "scope_sample_count": scope_n,
        "available_chapter_count": available,
        "chapters": chapters_info,
        "reason": reason,
        "scope_alignment": scope_preview,
    }


async def custom_report_block_reason(
    db: AsyncSession,
    *,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
    scope_sample_count: int = 0,
) -> str:
    """无数据拦截的根因说明：区分「筛选无样本 / 企业不在范围 / 企业缺该维度数据」。"""
    scope = " · ".join(p for p in (industry_l1, province) if p) or "全部样本"
    if not enterprise_ids:
        if scope_sample_count == 0:
            return f"「{scope}」筛选下没有匹配样本。"
        return f"「{scope}」范围下暂无该维度数据。"
    try:
        all_metrics = await assessment._ensure_cache(db)
    except Exception as exc:
        logger.debug("block reason cache unavailable: %s", exc)
        all_metrics = []
    ents = [m for m in all_metrics if m.enterprise_id in set(enterprise_ids)]
    names = "、".join(m.display_name or m.display_label or "该企业" for m in ents) or "该企业"
    if scope_sample_count == 0:
        return f"「{scope}」筛选下没有匹配样本（{names} 不在该范围）。"
    in_scope = any(
        (not industry_l1 or m.industry_l1 == industry_l1)
        and (not province or m.province == province)
        for m in ents
    )
    if not in_scope:
        actual = "、".join(
            f"{m.display_name or '该企业'}（{m.industry_l1 or '未知行业'}·{m.province or '未知地区'}）"
            for m in ents
        )
        return f"指定企业 {actual} 不在「{scope}」范围内，筛选条件冲突。"
    return f"「{names}」缺少该维度数据。"


async def available_custom_chapters(
    db: AsyncSession,
    functions: list[str],
    *,
    industry_l1: str | None = None,
    province: str | None = None,
) -> dict[str, bool]:
    """判定各可组合章节在当前范围是否有「安全 claim」（数据驱动空引导）。

    复用 _build_context_from_spec 的空章节判定：仅保留 computed/inferred 且可溯源的 claim，
    无安全 claim 的章节 → False。路由据此引导用户换范围/换章节，而非静默丢章节或报 500。
    """
    result: dict[str, bool] = {}
    for fn in functions:
        ok, _ = await _chapter_available(db, fn, industry_l1=industry_l1, province=province)
        result[fn] = ok
    return result


async def _build_context_from_spec(
    db: AsyncSession,
    *,
    key: str,
    spec: dict[str, Any],
    session_id: str | None = None,
    report_id: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> dict[str, Any]:
    """通用章节装配：给定场景 key + spec dict（固定场景或定制自由组合），产出报告上下文。

    章节循环按 spec["chapters"] 逐个复用 judgment_service 的 8 个 function builder，
    结论/评级始终由 L0/L1 统一给出；此处只决定「结构 + 语气」。
    """
    scope = scope_label(industry_l1, province)
    chapters = []
    chapter_claims: list[list[Claim]] = []

    try:
        attribution = await assessment.get_slice_attribution(db, industry_l1=industry_l1, enterprise_ids=enterprise_ids)
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
                    "purpose": compose_purpose_from_claims(
                        "会话内多维度结论汇总", ctx_syn
                    ),
                    "function": "synthesis",
                    "dimension": "overall",
                    "claims": ctx_syn,
                    "meta": syn_meta,
                    "charts": None,
                    "numeric_rows": _numeric_table_rows(ctx_syn),
                }
            )

    # 六维雷达：画像/预警主题前置；兼容旧 due_diligence/overview key。
    # 铁律（claim 唯一化）：雷达只展示正文确有解析的维度（雷达 ⊆ 章节）。
    radar_chart = (
        attribution_radar_chart(
            attribution,
            dims=radar_dimensions_for_chapters(spec["chapters"]),
        )
        if key in ("portrait", "alert", "due_diligence", "overview", "profile")
        else None
    )
    if radar_chart and attribution.get("summary"):
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
                "purpose": compose_purpose_from_claims(
                    "样本六个维度经营表现雷达画像", ctx_radar
                ),
                "function": "score",
                "dimension": "overall",
                "claims": ctx_radar,
                "meta": {
                    "attribution": attribution,
                    "sample_count": attribution.get("sample_count"),
                },
                "charts": radar_chart,
                "numeric_rows": _numeric_table_rows(ctx_radar),
            }
        )

    for ch in spec["chapters"]:
        claims, meta = await _chapter_claims(
            db, session_id, ch["function"], ch["dimension"],
            industry_l1=industry_l1, province=province, enterprise_ids=enterprise_ids,
        )
        safe = [c for c in claims if _is_real_data_claim(c)]
        if not safe:
            logger.debug("skip empty report chapter: %s", ch.get("title"))
            continue
        ctx_claims = _claims_to_ctx(safe)
        chapter_claims.append(safe)
        chapters.append(
            {
                "title": ch["title"],
                "purpose": compose_purpose_from_claims(ch["purpose"], ctx_claims),
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

    # 硬门禁：剥离不可溯源 claim + 违规解读句，再校验（管道：坏 message 不出表面文本）
    enforcement = hallucination_guard.enforce_chapter_integrity(chapters)

    attribution_chart_path: str | None = None
    if report_id:
        attr_path = REPORTS_DIR / "_charts" / report_id / "attribution.png"
        if render_dimension_attribution_png(attribution, attr_path):
            attribution_chart_path = str(attr_path)

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

    story = compose_story_from_chapters(chapters)
    summary_kpis, story, executive_summary, cross_enf = hallucination_guard.enforce_cross_surface(
        chapters=chapters,
        summary_kpis=summary_kpis,
        story=story,
        executive_summary=executive_summary,
    )
    cross_validation = hallucination_guard.validate_cross_surface(
        chapters=chapters,
        summary_kpis=summary_kpis,
        story=story,
        executive_summary=executive_summary,
    )

    validation = hallucination_guard.validate_report_chapters(chapters)
    validation["enforced"] = enforcement
    validation["cross_enforced"] = cross_enf
    validation["cross_surface"] = cross_validation
    if not cross_validation.get("ok"):
        validation["ok"] = False

    scope_n = int(attribution.get("sample_count") or 0)
    scope_align = hallucination_guard.validate_scope_sample_alignment(
        chapters,
        scope_sample_count=scope_n,
        industry_l1=industry_l1,
        province=province,
        enterprise_ids=enterprise_ids,
    )
    validation["scope_alignment"] = scope_align
    if not scope_align.get("ok"):
        validation["ok"] = False
        logger.error(
            "scope sample misalignment (industry=%s province=%s): %s",
            industry_l1,
            province,
            scope_align.get("mismatches"),
        )

    summary_block = _scenario_summary_block(chapters, attribution, high_risk_ids, scenario=key)
    firm_count_guard = hallucination_guard.validate_firm_counts_within_scope(
        scope_sample_count=scope_n,
        drag_factors=attribution.get("drag_factors") or [],
        summary_risks=summary_block.get("risks") or [],
        summary_strengths=summary_block.get("strengths") or [],
        texts=[
            summary_block.get("conclusion") or "",
            executive_summary or "",
            attribution.get("summary") or "",
        ],
    )
    validation["firm_count_guard"] = firm_count_guard
    if not firm_count_guard.get("ok"):
        validation["ok"] = False
        logger.error(
            "firm count exceeds sample (industry=%s n=%s): %s",
            industry_l1,
            scope_n,
            firm_count_guard.get("violations"),
        )

    # 封面：群体报告用「群体风险判断」，禁止单主体「风险等级」标签（规范书 §2.2）
    from app.services.scope_contract import SMALL_SAMPLE_N, small_sample_banner

    _avg = attribution.get("avg_score")
    _sample_banner = small_sample_banner(scope_n)
    from app.services.report_templates import sanitize_surface_industry_terms

    cover_meta = {
        "scenario_label": get_scenario_label(key),
        "risk_level": _score_to_risk_level(_avg) if isinstance(_avg, (int, float)) else "—",
        "business_level": business_level(_avg) if isinstance(_avg, (int, float)) else "—",
        "sample_count": str(attribution.get("sample_count") or "—"),
        "small_sample": scope_n > 0 and scope_n < SMALL_SAMPLE_N,
        "small_sample_banner": _sample_banner,
    }
    raw_title = f"{scope} · {spec['title']}" if scope else spec["title"]
    context = {
        "scenario": key,
        "scenario_label": get_scenario_label(key),
        "tier": get_scenario_tier(key),
        "title": sanitize_surface_industry_terms(raw_title),
        "subtitle": sanitize_surface_industry_terms(spec.get("subtitle", "")),
        "scope": scope or None,
        "story": sanitize_surface_industry_terms(story or ""),
        # 五场景差异化元数据：封面母题/主色 + 数据类侧重 + 场景 KPI 卡定义（L3/L4）
        "cover": spec.get("cover") or {"motif": "compass", "accent": "#003366"},
        "data_focus": list(spec.get("data_focus") or []),
        "scenario_kpis": scenario_kpis,
        "report_date": _now_cn().strftime("%Y年%m月%d日"),
        "chapters": chapters,
        "summary_kpis": summary_kpis,
        "executive_summary": sanitize_surface_industry_terms(
            f"{_sample_banner}{executive_summary}"
            if _sample_banner and executive_summary and _sample_banner not in executive_summary
            else (_sample_banner or executive_summary)
        ),
        "summary_conclusion": (
            f"{_sample_banner}{summary_block['conclusion']}"
            if _sample_banner
            and summary_block.get("conclusion")
            and _sample_banner not in (summary_block.get("conclusion") or "")
            else summary_block["conclusion"]
        ),
        "summary_strengths": summary_block["strengths"],
        "summary_risks": summary_block["risks"],
        # 末尾「核心要点」：只留短标签，避免与执行摘要大段重复
        "summary_highlights": _summary_highlight_labels(
            summary_block.get("strengths") or [],
            summary_block.get("risks") or [],
        ),
        "cover_meta": cover_meta,
        "attribution": attribution,
        "attribution_brief": _attribution_brief(attribution),
        "threshold_board": (
            financial_benchmarks.FINANCIAL_THRESHOLD_TABLE()
            if key in ("alert", "financial", "tax", "fraud", "due_diligence")
            else []
        ),
        "attribution_chart": attribution_chart_path,
        "period_count": 1,  # 聚合快照默认单期；≥2 期才允许时序词
        "validation": validation,
    }
    _dedupe_chapter_surface_text(context.get("chapters") or [])
    _compact_chapter_narrations(context.get("chapters") or [])
    _apply_temporal_gate(context)
    for ch in context.get("chapters") or []:
        ch["numeric_rows"] = _numeric_table_rows(ch.get("claims") or [])
    _sanitize_slice_context_surfaces(context)
    lexicon = hallucination_guard.validate_surface_lexicon(context, report_kind="slice")
    validation["lexicon"] = lexicon
    if not lexicon.get("ok"):
        validation["ok"] = False
    return context


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

    # 封面（与个体报告统一：品牌 → 标题 → 分隔线 → 元数据 → 日期/编号；无 doc-type/层级/密级）
    cover_meta = context.get("cover_meta") or {}
    pdf.add_page()
    pdf.start_section("封面")
    pdf.ln(40)
    _para(pdf, "明鉴 · 财税票 · 万景", size=12, h=8, align="C")
    pdf.ln(40)
    _para(pdf, context["title"], size=20, h=11, align="C")
    pdf.ln(34)
    for line in (
        f"报告场景：{cover_meta.get('scenario_label') or context.get('scenario_label', context['scenario'])}",
        f"群体风险判断：{cover_meta.get('risk_level') or '—'}",
        f"综合经营表现：{cover_meta.get('business_level') or '—'}",
        f"样本规模：{cover_meta.get('sample_count') or '—'} 家",
    ):
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=11)
        pdf.cell(_text_w(pdf), 8, line, ln=True, align="C")
    pdf.ln(30)
    for line in (f"报告日期：{context['report_date']}", f"报告编号：{zh_report_no(report_id)}"):
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=10)
        pdf.cell(_text_w(pdf), 8, line, ln=True, align="C")

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
        kpis = [k for k in (context.get("summary_kpis") or []) if k.get("value") not in ("—", "")]
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
            if not items:
                continue  # 空模块不出现（不写「无数据」占位）
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, head, ln=True)
            pdf.set_font(fn, size=10)
            for it in items:
                _para(pdf, f"- {it}", size=10, h=5)
            pdf.ln(2)

        if exec_summary:
            _para(pdf, exec_summary, size=11, h=6)
            pdf.ln(3)
        _para(pdf, "本报告为聚合切片，各模块统计子集不同，详见各章节标注。", size=9, h=5)

    # 归因章节（画像/预警主题；流式不强制 add_page）
    attr = context.get("attribution") or {}
    board = context.get("threshold_board") or []
    if board and context.get("scenario") in ("alert", "financial", "tax", "fraud", "due_diligence"):
        pdf.start_section("预警阈值一览")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "预警阈值一览", ln=True)
        _para(pdf, "本报告为匿名聚合：披露命中家数与信号分布，不输出具名企业名单。", size=9, h=5)
        _table(
            pdf,
            ["指标", "能力组", "判定规则", "阈值"],
            [
                [
                    str(r.get("label") or "【暂无可用数据】"),
                    str(r.get("group") or "【暂无可用数据】"),
                    str(r.get("rule") or "【暂无可用数据】"),
                    str(r.get("threshold") or "【暂无可用数据】"),
                ]
                for r in board
            ],
            [0.28, 0.18, 0.36, 0.18],
            size=9,
        )
        pdf.ln(3)

    if context.get("scenario") in ("alert", "due_diligence", "portrait", "overview", "profile") and (
        context.get("attribution_brief") or attr.get("summary")
    ):
        pdf.start_section("维度归因 · 为什么")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "维度归因 · 为什么", ln=True)
        _para(pdf, context.get("attribution_brief") or attr.get("summary") or "", size=11, h=6)
        pdf.ln(3)

        drag = attr.get("drag_factors") or []
        if drag:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "主要拖累因素", ln=True)
            pdf.set_font(fn, size=10)
            for d in drag[:6]:
                pdf.set_x(pdf.l_margin)
                n = int(d.get("count") or 0)
                sample = attr.get("sample_count")
                if sample:
                    try:
                        sn = int(sample)
                        pct = min(100.0, round(n / sn * 100, 1)) if sn > 0 else 0.0
                        label = f"- {d.get('item', '')}（{n} 家 / 样本 {sn} 家（{pct:.1f}%））"
                    except (TypeError, ValueError):
                        label = f"- {d.get('item', '')}（{n} 家）"
                else:
                    label = f"- {d.get('item', '')}（{n} 家）"
                pdf.cell(_text_w(pdf), 6, label, ln=True)
            pdf.ln(3)

        attr_chart = context.get("attribution_chart")
        if attr_chart and Path(attr_chart).exists():
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "六维经营表现", ln=True)
            try:
                pdf.image(attr_chart, w=min(_text_w(pdf), 180))
                pdf.ln(4)
            except Exception as exc:
                logger.debug("attribution chart skip: %s", exc)

        dims = attr.get("dimensions") or {}
        if dims:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "维度经营表现", ln=True)
            _table(
                pdf,
                ["维度", "本维指数", "经营表现"],
                [
                    [
                        str(d.get("label", "")),
                        f"{float(d.get('score') or 0):.1f}",
                        business_level(float(d.get("score") or 0)),
                    ]
                    for d in dims.values()
                ],
                [0.4, 0.25, 0.35],
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
        for line in _chapter_conclusion_lines(ch):
            _para(pdf, f"- {line}", size=11, h=6)
        pdf.ln(2)

    # 核心要点提炼（短标签，避免与执行摘要大段重复）
    highlights = context.get("summary_highlights") or {}
    signals = highlights.get("strengths") or context.get("summary_strengths") or []
    warnings = highlights.get("risks") or context.get("summary_risks") or []
    if signals or warnings:
        pdf.add_page()
        pdf.start_section("核心要点提炼")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "核心要点提炼", ln=True)
        if signals:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "【经营信号】", ln=True)
            pdf.set_font(fn, size=11)
            for s in signals:
                _para(pdf, f"- {s}", size=11, h=6)
        if warnings:
            pdf.ln(2)
            pdf.set_x(pdf.l_margin)
            pdf.set_font(fn, size=12)
            pdf.cell(_text_w(pdf), 8, "【风险预警点】", ln=True)
            pdf.set_font(fn, size=11)
            for r in warnings:
                _para(pdf, f"- {r}", size=11, h=6)

    _para(
        pdf,
        "本报告由明鉴・财税票・万景自动生成。无数据处弃权、不编造，仅供内部风控参考。",
        size=10,
        h=5,
    )

    pdf.output(str(output_path))


def _generate_slice_pdf(context: dict[str, Any], report_id: str, output_path: Path) -> None:
    if try_generate_weasyprint_pdf(context, report_id, output_path):
        _cleanup_chart_dir(report_id)
        return
    # FPDF 降级：仍跑上下文表面后置校验，禁止脏报告绕过
    from app.services.report_preflight import run_postflight_context, write_validation_log

    post = run_postflight_context(context)
    write_validation_log(
        report_id,
        reports_dir=output_path.parent,
        preflight=context.get("preflight"),
        postflight=post,
    )
    if not post.get("ok"):
        raise ValueError(
            "报告后置校验未通过（FPDF 路径），拒绝生成 PDF。"
            f"详情：{(post.get('context') or {}).get('hard')}"
        )
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
    _para(pdf, f"企业名称：{subject.get('name') or ('样本 #' + str(subject.get('short_id', '—')))}", size=13, h=7, align="C")
    pdf.ln(2)
    _para(pdf, f"风险等级：{overall.get('risk_level', '—')}", size=13, h=7, align="C")
    pdf.ln(2)
    _para(pdf, f"评级展望：{overall.get('outlook', '—')}", size=13, h=7, align="C")
    pdf.ln(14)
    _para(pdf, f"报告日期：{context.get('report_date', '')}", size=11, h=6, align="C")
    _para(pdf, f"报告编号：{zh_report_no(report_id)}", size=11, h=6, align="C")

    # 评级摘要（结论前置：等级 + 展望 + 优势/风险 + 成段理由）
    pdf.add_page()
    pdf.start_section("评级摘要")
    _h(pdf, "评级摘要")
    _score = overall.get("overall_score")
    _kv(pdf, "风险等级", overall.get("risk_level", "—"))
    _kv(pdf, "评级展望", overall.get("outlook", "—"))
    _kv(pdf, "综合经营表现", business_level(float(_score)) if _score is not None else "—")
    pdf.ln(3)
    _para(pdf, overall.get("reason") or "", size=11, h=6)

    # 六维风险画像（雷达图 + 结论前置解读）
    radar_path = context.get("radar_chart")
    if radar_path and Path(radar_path).exists():
        pdf.ln(3)
        try:
            pdf.image(str(radar_path), x=pdf.l_margin, w=_tw(pdf) * 0.6)
        except Exception as exc:  # 图渲染失败不阻断报告输出
            logger.debug("radar chart image failed: %s", exc)
    radar_interpretation = overall.get("radar_interpretation")
    if radar_interpretation:
        pdf.ln(3)
        _para(pdf, radar_interpretation, size=10, h=6)

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
            _para(pdf, f"· {_strip_bullet_prefix(str(it))}", size=10, h=6)

    # 一、企业基本信息
    pdf.add_page()
    pdf.start_section("一、企业基本信息")
    _h(pdf, "一、企业基本信息")
    _kv(pdf, "企业名称", subject.get("name") or f"样本 #{subject.get('short_id') or ''}")
    if subject.get("industry_l1") or subject.get("industry_l2"):
        _kv(pdf, "所属行业", f"{subject.get('industry_l1') or ''} / {subject.get('industry_l2') or ''}")
    if subject.get("province"):
        _kv(pdf, "所属地区", subject["province"])
    if subject.get("report_year"):
        _kv(pdf, "报告年度", subject["report_year"])

    # 二、六维风险分析（与雷达同源）
    six_dims = context.get("six_dimensions") or []
    if six_dims:
        pdf.add_page()
        pdf.start_section("二、六维风险分析")
        _h(pdf, "二、六维风险分析")
        for i, dim in enumerate(six_dims, 1):
            pdf.ln(2)
            _h(pdf, f"二.{i} {dim['title']}", size=12)
            _kv(pdf, "风险等级", dim.get("risk_level", "—"))
            pdf.ln(1)
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
                [0.28, 0.18, 0.34, 0.2],
            )
            pdf.ln(2)
            an = dim.get("analysis") or {}
            if an.get("level_review"):
                _para(pdf, an["level_review"], size=10, h=6)
            if an.get("risks"):
                _para(pdf, f"风险识别：{an['risks']}", size=10, h=6)
            if an.get("trend"):
                _para(pdf, f"趋势：{an['trend']}", size=10, h=6)
            if an.get("advice"):
                _para(pdf, f"建议：{an['advice']}", size=10, h=6)

    # 三、财务能力明细（资本结构→偿债→盈利→现金流→营运→成长）
    fin_dims = context.get("dimensions") or []
    if fin_dims:
        pdf.add_page()
        pdf.start_section("三、财务能力明细")
        _h(pdf, "三、财务能力明细")
        for i, dim in enumerate(fin_dims, 1):
            pdf.ln(2)
            _h(pdf, f"三.{i} {dim['title']}", size=12)
            _kv(pdf, "风险等级", dim.get("risk_level", "—"))
            pdf.ln(1)
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
            pdf.ln(2)
            an = dim.get("analysis") or {}
            if an.get("level_review"):
                _para(pdf, an["level_review"], size=10, h=6)
            if an.get("risks"):
                _para(pdf, f"越线依据：{an['risks']}", size=10, h=6)
            if an.get("trend"):
                _para(pdf, f"趋势：{an['trend']}", size=10, h=6)
            if an.get("advice"):
                _para(pdf, f"建议：{an['advice']}", size=10, h=6)

    # 四、主要财务数据（三表齐全，空表保留【暂无可用数据】，序号连续）
    statements = context.get("statements")
    sec_n = 0
    if statements:
        pdf.add_page()
        pdf.start_section("四、主要财务数据")
        _h(pdf, "四、主要财务数据")
        for st in ("income", "balance", "cashflow"):
            s = statements.get(st) or {}
            rows = s.get("rows") or [["【暂无可用数据】", "—"]]
            sec_n += 1
            pdf.ln(2)
            _h(pdf, f"四.{sec_n} {s.get('title', st)}（单位：万元）", size=12)
            _table(
                pdf,
                ["项目", "金额（万元）"],
                [[str(row[0]), str(row[1])] for row in rows],
                [0.6, 0.4],
            )

    # 杜邦 / 同业对标：接续四.x 序号
    dupont = context.get("dupont")
    if dupont:
        sec_n += 1
        pdf.add_page()
        pdf.start_section(f"四.{sec_n} 杜邦分解")
        _h(pdf, f"四.{sec_n} 杜邦分解")
        _para(pdf, dupont.get("formula") or "", size=11, h=7)
        for f in dupont.get("factors") or []:
            _para(
                pdf,
                f"· {f.get('label', '')}（{f.get('dir', '')}）：{f.get('disp', '')}",
                size=10, h=6,
            )
        _para(pdf, f"净资产收益率：{dupont.get('roe_disp', '')}", size=10, h=6)
        factors = dupont.get("factors") or []
        if len(factors) >= 3:
            _para(
                pdf,
                f"净资产收益率 {dupont.get('roe_disp')} = 净利率 {factors[0]['disp']} × 总资产周转率 {factors[1]['disp']} × 权益乘数 {factors[2]['disp']}。",
                size=10, h=6,
            )

    benchmark_chart = context.get("benchmark_chart")
    if benchmark_chart and Path(benchmark_chart).exists():
        sec_n += 1
        pdf.add_page()
        pdf.start_section(f"四.{sec_n} 同业对标")
        _h(pdf, f"四.{sec_n} 同业对标（本样本 对比 行业均值，%）")
        bench_interpretation = context.get("benchmark_interpretation")
        if bench_interpretation:
            _para(pdf, bench_interpretation, size=10, h=6)
            pdf.ln(2)
        try:
            pdf.image(str(benchmark_chart), x=pdf.l_margin, w=_tw(pdf))
        except Exception as exc:
            logger.debug("benchmark chart image failed: %s", exc)

    # 免责声明
    pdf.ln(6)
    _para(
        pdf,
        "本报告由明鉴・财税票・万景自动生成。无数据处弃权、不编造，仅供内部风控参考。",
        size=10,
        h=5,
    )

    pdf.output(str(output_path))


def _generate_enterprise_pdf(context: dict[str, Any], report_id: str, output_path: Path) -> None:
    if try_generate_weasyprint_pdf(context, report_id, output_path):
        _cleanup_chart_dir(report_id)
        return
    from app.services.report_preflight import run_postflight_context, write_validation_log

    post = run_postflight_context(context)
    write_validation_log(
        report_id,
        reports_dir=output_path.parent,
        preflight=context.get("preflight"),
        postflight=post,
    )
    if not post.get("ok"):
        raise ValueError(
            "报告后置校验未通过（FPDF 路径），拒绝生成 PDF。"
            f"详情：{(post.get('context') or {}).get('hard')}"
        )
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
    _assert_report_renderable(context)
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
    enterprise_ids: list[str] | None = None,
) -> tuple[str, Path, dict[str, Any]]:
    """对话式定制报告：把 AI 判定的章节有序子集转成 spec dict，走通用章节装配 + PDF 渲染。

    不经过 resolve_scenario / _canonical，避免 custom→due_diligence 旧映射干扰。
    章节自由组合，但每章结论/评级仍由 L0/L1 统一给出（铁律：AI 只决定结构，不产数字）。
    """
    from app.services.custom_report import normalize_spec, spec_to_report_spec

    cleanup_legacy_reports()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    # 生成前再规范化一次：标题行业代码→中文，避免 lexicon 硬拒（如 IT软件）
    spec = normalize_spec(spec) or spec
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
        enterprise_ids=enterprise_ids,
    )
    if not context.get("chapters") or int(
        (context.get("attribution") or {}).get("sample_count") or 0
    ) <= 0:
        raise ValueError("当前切片无有效样本数据，无法生成定制报告。请先接入并确认数据。")
    _assert_report_renderable(context)
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
        "advice": "资产负债率已过 70% 警戒线，杠杆偏高；优先压降负债，并核查举债结构是否稳健。",
    },
    {
        "key": "solvency", "title": "偿债能力",
        "fields": ["current_ratio", "quick_ratio"],
        "advice": "流动/速动比率跌破阈值，短期偿债承压；核查再融资能力与到期债务接续安排。",
    },
    {
        "key": "profitability", "title": "盈利能力",
        "fields": ["gross_margin", "net_margin", "roe", "roa"],
        "advice": "净利率本期偏低，成本结构或定价能力有缺口；核查毛利来源，净资产收益率为负时股东回报承压。",
    },
    {
        "key": "cashflow", "title": "现金流",
        "fields": ["operating_cf", "investing_cf", "financing_cf"],
        "advice": "经营现金流为负，自身造血不足；核查回款质量与垫资规模，警惕对外融资依赖。",
    },
    {
        "key": "operation", "title": "营运能力",
        "fields": ["receivables_turnover", "inventory_turnover", "asset_turnover"],
        "advice": "应收与存货周转偏低，资金被占用；收紧回款周期、加快存货去化。",
    },
    {
        "key": "growth", "title": "成长能力",
        "fields": ["revenue_yoy", "profit_yoy"],
        "advice": "营收与净利同比为负，成长承压；增长与盈利背离时，先查增长质量。",
    },
]

_CASH_FLOW_LABELS: dict[str, str] = {
    "operating_cf": "经营活动现金流量净额",
    "investing_cf": "投资活动现金流量净额",
    "financing_cf": "筹资活动现金流量净额",
}
_CASH_FLOW_STANDARD: dict[str, str] = {"operating_cf": "≥0", "investing_cf": "", "financing_cf": ""}


def _fmt_wan(amount: Any) -> str:
    """金额（元）→ 万元字符串，匹配样张「单位：万元」。"""
    try:
        v = float(amount or 0)
    except (TypeError, ValueError):
        return "—"
    return f"{v / 10000:,.2f}"


def _dim_risk_level(warn: int, passed: int, total: int) -> tuple[str, str]:
    """维度风险等级：有预警→高；其余达标→低（空维度在调用前已弃权，不会进入）。"""
    if warn > 0:
        return "高", "#d32f2f"
    return "低", "#2e7d32"


def _dimension_analysis(
    key: str,
    metrics: list[dict[str, str]],
    warn: int,
    passed: int,
    risk: str,
    total: int | None = None,
) -> dict[str, str]:
    """维度风险解读（结论前置，风控专家口吻）：先给判断，再给越线依据与动作。"""
    total = len(metrics) if total is None else total
    dim_title = next((s["title"] for s in _REPORT_DIMENSIONS if s["key"] == key), key)
    anomaly_items = [m for m in metrics if m["rating"] == "账务异常"]
    invalid_items = [m for m in metrics if m["rating"] in ("计算失效", "资不抵债")]
    warn_items = [m for m in metrics if m["rating"] == "预警"]
    issue_items = anomaly_items + invalid_items + warn_items

    if anomaly_items or invalid_items:
        lead = "、".join(m["label"] for m in (anomaly_items + invalid_items))
        level_review = (
            f"{dim_title}整体风险「{risk}」：{lead}出现账务异常或计算失效，"
            f"不得按普通达标/预警口径采信，须先核原始报表。"
        )
        risks = "；".join(
            f"{m['label']} {m['value']}（{m.get('standard') or m['rating']}）"
            for m in issue_items
        ) + "。"
    elif warn_items:
        lead = "、".join(m["label"] for m in warn_items)
        level_review = f"{dim_title}整体风险「{risk}」：{lead}越线，需优先核查。"
        risks = "；".join(
            f"{m['label']} {m['value']}（标准 {m['standard']}）" for m in warn_items
        ) + "。"
    else:
        level_review = f"{dim_title}整体风险「{risk}」：{total} 项指标均达标，未见明显异常。"
        risks = ""

    if key == "growth":
        vals = [f"{m['label']} {m['value']}" for m in metrics]
        trend = f"{'、'.join(vals)}。" if vals else ""
    else:
        trend = ""

    # 铁律（claim 唯一化）：风险建议必须绑定指标预警/账务异常/计算失效。达标 → 不输出风险建议。
    if anomaly_items or invalid_items:
        advice = "建议逐项核对原始报表科目与勾稽关系；权益为负时 ROE 等指标计算失效，排除取数/口径错误后再评级。"
    elif warn_items:
        advice = next((s["advice"] for s in _REPORT_DIMENSIONS if s["key"] == key), "")
    else:
        advice = ""
    return {"level_review": level_review, "trend": trend, "risks": risks, "advice": advice}


def _parse_display_number(value: str | None) -> float | None:
    """从展示串（含 % / 万元 / 千分位）提取数字，供个体报告校验锚点。"""
    if not value or value in ("—", "-"):
        return None
    s = str(value).replace(",", "").replace("%", "").replace("万元", "").strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _enterprise_chapters_for_validation(
    *,
    dimensions: list[dict[str, Any]],
    risk_points: list[str],
    reason: str,
    overall_score: float | None,
) -> list[dict[str, Any]]:
    """把个体报告维度/风险点转成 claim 章结构，复用 validate_report_chapters（禁止假 ok）。"""
    chapters: list[dict[str, Any]] = []
    overall_claims: list[Claim] = []
    if overall_score is not None:
        overall_claims.append(
            Claim(
                claim=f"综合经营表现「{business_level(float(overall_score))}」。",
                value=ClaimValue(
                    metric="overall_score",
                    number=round(float(overall_score), 2),
                    unit="分",
                ),
                trace=ClaimTrace(
                    table="assessment",
                    field="overall_score",
                    query_id="Q_ent_overall",
                ),
                confidence="computed",
            )
        )
    for rp in risk_points:
        text = rp if str(rp).endswith(("。", "！", "？")) else f"{rp}。"
        overall_claims.append(
            Claim(
                claim=text,
                value=ClaimValue(metric="risk_point", number=None, unit=""),
                trace=ClaimTrace(
                    table="insight_engine",
                    field="insight",
                    query_id="Q_ent_risk_point",
                ),
                confidence="computed",
            )
        )
    # 评级理由作为 claim（非 narration），避免「承压」类措辞在无风险 claim 时被判矛盾
    if reason:
        rtext = reason if str(reason).endswith(("。", "！", "？")) else f"{reason}。"
        overall_claims.append(
            Claim(
                claim=rtext,
                value=ClaimValue(metric="rating_reason", number=None, unit=""),
                trace=ClaimTrace(
                    table="assessment",
                    field="risk_level",
                    query_id="Q_ent_reason",
                ),
                confidence="computed",
            )
        )
    if overall_claims:
        chapters.append(
            {
                "title": "总体风险评估",
                "claims": [c.model_dump() for c in overall_claims],
                "narration": "",
            }
        )

    for dim in dimensions:
        claims: list[Claim] = []
        for m in dim.get("metrics") or []:
            label = m.get("label") or "指标"
            val = m.get("value") or "—"
            rating = m.get("rating") or ""
            num = _parse_display_number(val)
            unit = m.get("unit") or ""
            rating_tail = f"，{rating}" if rating else ""
            claims.append(
                Claim(
                    claim=f"{label} {val}{unit}{rating_tail}。",
                    value=ClaimValue(
                        metric=str(label),
                        number=num,
                        unit=unit,
                    ),
                    trace=ClaimTrace(
                        table="enterprise_financials",
                        field=str(label),
                        query_id="Q_ent_dim_metric",
                    ),
                    confidence="computed",
                )
            )
        analysis = dim.get("analysis") or {}
        # 规则引擎解读升格为 claim（禁止塞进 narration 再被当成 LLM 润色做数字/方向校验）
        for key, qid in (
            ("level_review", "Q_ent_dim_review"),
            ("trend", "Q_ent_dim_trend"),
            ("risks", "Q_ent_dim_risks"),
            ("advice", "Q_ent_dim_advice"),
        ):
            text = (analysis.get(key) or "").strip()
            if not text:
                continue
            if not text.endswith(("。", "！", "？")):
                text = f"{text}。"
            nums = [
                _parse_display_number(n)
                for n in re.findall(r"-?\d+(?:\.\d+)?", text)
            ]
            nums = [n for n in nums if n is not None]
            claims.append(
                Claim(
                    claim=text,
                    value=ClaimValue(
                        metric=f"dim_{key}",
                        number=nums[0] if nums else None,
                        unit="",
                    ),
                    trace=ClaimTrace(
                        table="assessment",
                        field=key,
                        query_id=qid,
                    ),
                    confidence="computed",
                    evidence_chain=[f"n={n}" for n in nums[:8]],
                )
            )
        if not claims:
            continue
        chapters.append(
            {
                "title": dim.get("title") or dim.get("key") or "维度",
                "claims": [c.model_dump() for c in claims],
                "narration": "",  # 规则引擎正文已在 claims；空 narration 避免误跑 LLM 解读校验
            }
        )
    return chapters


def _validate_enterprise_context(
    *,
    dimensions: list[dict[str, Any]],
    risk_points: list[str],
    reason: str,
    overall_score: float | None,
) -> dict[str, Any]:
    chapters = _enterprise_chapters_for_validation(
        dimensions=dimensions,
        risk_points=risk_points,
        reason=reason,
        overall_score=overall_score,
    )
    return hallucination_guard.validate_report_chapters(chapters)


def _build_dimension_sections(
    fin: EnterpriseFinancials | None, has_fin: bool
) -> list[dict[str, Any]]:
    dims: list[dict[str, Any]] = []
    owner_equity = float(getattr(fin, "owner_equity", 0) or 0) if has_fin and fin else 0.0
    for spec in _REPORT_DIMENSIONS:
        key = spec["key"]
        fields = spec["fields"]
        metrics: list[dict[str, str]] = []
        warn = passed = 0
        rated_total = 0
        for field in fields:
            raw = float(getattr(fin, field) or 0) if has_fin else 0.0
            if key == "cashflow":
                if raw == 0.0:
                    continue  # 无值现金流不出现
                label = _CASH_FLOW_LABELS[field]
                standard = _CASH_FLOW_STANDARD[field]
                if field == "operating_cf":
                    rated_total += 1
                    if raw < 0:
                        rating = "预警"
                        warn += 1
                    else:
                        rating = "达标"
                        passed += 1
                else:
                    rating = ""  # 投/筹资现金流仅展示，不评级
                metrics.append(
                    {"label": label, "value": _fmt_wan(raw), "unit": "万元", "standard": standard, "rating": rating}
                )
            else:
                cfg = financial_benchmarks.FINANCIAL_RATIOS[field]
                disp = financial_benchmarks.format_financial_ratio(
                    field, raw, owner_equity=owner_equity
                )
                # is_pct 展示值已含 %（format_financial_ratio），unit 置空避免「%%」双写
                unit = cfg["unit"] if not cfg.get("is_pct") else ""
                if cfg.get("warn_dir") is None:
                    # 仅展示项（roa/asset_turnover/profit_yoy）：无值不出现；有值展示，参考标准/评级留空
                    if raw == 0.0:
                        continue
                    metrics.append(
                        {"label": cfg["label"], "value": disp, "unit": unit, "standard": "", "rating": ""}
                    )
                    continue
                if raw == 0.0 and not financial_benchmarks.is_equity_based_ratio_invalid(
                    field, owner_equity=owner_equity
                ):
                    continue  # 无值评级指标不出现；权益为负 ROE 即使存值也要展示失效
                if financial_benchmarks.is_equity_based_ratio_invalid(
                    field, owner_equity=owner_equity
                ):
                    rated_total += 1
                    warn += 1
                    metrics.append(
                        {
                            "label": cfg["label"],
                            "value": disp,
                            "unit": "",
                            "standard": "所有者权益为负，ROE 分母失效",
                            "rating": "计算失效",
                        }
                    )
                    continue
                if raw == 0.0:
                    continue
                rated_total += 1
                rating = financial_benchmarks.assess_financial_ratio(
                    field, raw, owner_equity=owner_equity
                )
                if rating in ("预警", "账务异常", "计算失效"):
                    warn += 1
                elif rating == "达标":
                    passed += 1
                metrics.append(
                    {
                        "label": cfg["label"],
                        "value": disp,
                        "unit": unit,
                        "standard": _threshold_text(cfg) or "",
                        "rating": rating,
                    }
                )
        # 仅展示金额（资本结构：资产/负债/权益规模，万元），无值不出现
        for label, col in spec.get("amounts") or []:
            raw = float(getattr(fin, col) or 0) if has_fin else 0.0
            if raw == 0.0:
                continue
            anomalous = financial_benchmarks.is_anomalous_amount(col, raw)
            equity_neg = col == "owner_equity" and raw < 0
            if anomalous or equity_neg:
                rated_total += 1
                warn += 1
            metrics.append(
                {
                    "label": label,
                    "value": _fmt_wan(raw),
                    "unit": "万元",
                    "standard": (
                        "负债类金额应为非负"
                        if anomalous
                        else ("所有者权益为负，资不抵债" if equity_neg else "")
                    ),
                    "rating": (
                        "账务异常" if anomalous else ("资不抵债" if equity_neg else "")
                    ),
                }
            )
        # 空维度不出现；无任何可评级指标也无法下结论 → 弃权不出现
        if not metrics or rated_total == 0:
            continue
        risk, color = _dim_risk_level(warn, passed, rated_total)
        dims.append(
            {
                "key": key,
                "title": spec["title"],
                "risk_level": risk,
                "risk_color": color,
                "metrics": metrics,
                "analysis": _dimension_analysis(key, metrics, warn, passed, risk, total=rated_total),
            }
        )
    return dims


def _build_statements(fin: EnterpriseFinancials | None, has_fin: bool) -> dict[str, Any] | None:
    """三大财务报表：无报表 → None；有报表时三表齐全（空表保留标题+【暂无可用数据】，序号不跳号）。"""
    if not has_fin or fin is None:
        return None

    def _rows(items: list[tuple[str, str]]) -> list[list[str]]:
        out: list[list[str]] = []
        for label, col in items:
            raw = float(getattr(fin, col) or 0)
            if raw == 0.0:
                # 字段存在但值为空：显式占位，禁止空白单元格
                out.append([label, "【暂无可用数据】"])
                continue
            cell = _fmt_wan(raw)
            if financial_benchmarks.is_anomalous_amount(col, raw):
                cell = f"{cell}【账务异常】"
            out.append([label, cell])
        return out

    income_rows = _rows(_INCOME_STATEMENT)
    balance_rows = _rows(_BALANCE_SHEET)
    cash_rows = _rows(_CASH_FLOW)
    return {
        "income": {
            "title": "利润表",
            "rows": income_rows or [["【暂无可用数据】", "【暂无可用数据】"]],
            "empty": all(r[1] == "【暂无可用数据】" for r in income_rows) if income_rows else True,
        },
        "balance": {
            "title": "资产负债表",
            "rows": balance_rows or [["【暂无可用数据】", "【暂无可用数据】"]],
            "empty": all(r[1] == "【暂无可用数据】" for r in balance_rows) if balance_rows else True,
        },
        "cashflow": {
            "title": "现金流量表",
            "rows": cash_rows or [["【暂无可用数据】", "【暂无可用数据】"]],
            "empty": all(r[1] == "【暂无可用数据】" for r in cash_rows) if cash_rows else True,
        },
    }


_SIX_DIM_INSIGHT_CAT: dict[str, str] = {
    "tax_health": "税务",
    "authenticity": "真实性",
    "invoice": "发票",
    "finance": "财务",
    "legal": "司法",
    "industry": "综合",
}


def _score_to_dim_risk(score: float) -> tuple[str, str]:
    if score < 40:
        return "高", "#c62828"
    if score < 60:
        return "中等", "#f57c00"
    return "低", "#2e7d32"


def _build_six_dim_sections(
    profile: dict[str, Any],
    insights: list[Any],
    *,
    has_yoy: bool = False,
) -> list[dict[str, Any]]:
    """六维风险分析正文（与雷达同源）：有分才出章，保证雷达 ⊆ 章节。

    时序/同比提示不写入各子章（由模板在章首统一输出一次，避免重复）。
    """
    from app.services.assessment_weights import DIMENSION_LABELS, DIMENSION_WEIGHTS

    scores = profile.get("dimensions") or {}
    sections: list[dict[str, Any]] = []
    for key in DIMENSION_WEIGHTS:
        raw = scores.get(key)
        if not isinstance(raw, (int, float)) or float(raw) <= 0:
            continue
        score = float(raw)
        label = DIMENSION_LABELS.get(key, key)
        risk, color = _score_to_dim_risk(score)
        cat = _SIX_DIM_INSIGHT_CAT.get(key, "")
        related = [i for i in insights if getattr(i, "category", "") == cat][:2]
        level_review = f"「{label}」本维指数 {score:.1f}，风险等级「{risk}」。"
        risks = ""
        advice = ""
        if related:
            risks = "；".join(f"{i.title}（{i.fact_text()}）" for i in related)
            advice = related[0].advice or ""
        elif risk == "高":
            risks = f"该维度明显承压（本维指数 {score:.1f}），建议优先核查相关业务与数据口径。"
            advice = "建议结合原始凭证与同业基准交叉核实。"
        elif risk == "低":
            level_review = f"「{label}」本维指数 {score:.1f}，表现相对稳健，本维度指标未见显著风险。"
        sections.append(
            {
                "key": key,
                "title": label,
                "risk_level": risk,
                "risk_color": color,
                "score": round(score, 1),
                "metrics": [
                    {
                        "label": "本维指数",
                        "value": f"{score:.1f}",
                        "unit": "",
                        "standard": "≥60 偏低风险 · <40 高风险",
                        "rating": risk,  # 高 / 中等 / 低，禁止空白
                    }
                ],
                "analysis": {
                    "level_review": level_review,
                    "risks": risks,
                    "trend": "",
                    "advice": advice,
                },
            }
        )
    return sections


def _six_dim_temporal_note(*, has_yoy: bool) -> str:
    """六维章首时序提示（全文只输出一次）。"""
    if has_yoy:
        return "已纳入同比类指标解读；详见「财务能力明细」中的营收/利润同比。"
    return "本报告仅提供单年度数据，无可对比的上年历史数据，无法开展同比趋势分析。"


def _build_dupont(fin: EnterpriseFinancials | None, has_fin: bool) -> dict[str, Any] | None:
    """杜邦分解（ROE 三因子）；无报表/任一因子缺值 → None（弃权，不展示带空值部分）。"""
    if not has_fin or fin is None:
        return None
    result = financial_benchmarks.dupont_breakdown(
        net_margin=getattr(fin, "net_margin", 0),
        asset_turnover=getattr(fin, "asset_turnover", 0),
        total_assets=getattr(fin, "total_assets", 0),
        owner_equity=getattr(fin, "owner_equity", 0),
        roe=getattr(fin, "roe", 0),
    )
    return result if result.get("complete") else None


def _build_benchmark_chart(
    fin: EnterpriseFinancials | None, has_fin: bool, bench: IndustryBenchmark | None
) -> dict[str, Any] | None:
    """同业对标柱状图（本样本 vs 行业均值，百分比类比率）；账务异常/计算失效指标不参与绘图。"""
    if not has_fin or fin is None or bench is None:
        return None
    owner_equity = float(getattr(fin, "owner_equity", 0) or 0)
    labels, own_vals, bench_vals = [], [], []
    skipped: list[str] = []
    for field, bfield in _BENCH_PCT_RATIOS:
        own = float(getattr(fin, field) or 0)
        if own == 0.0 and not financial_benchmarks.is_equity_based_ratio_invalid(
            field, owner_equity=owner_equity
        ):
            continue
        label = financial_benchmarks.FINANCIAL_RATIOS[field]["label"]
        rating = financial_benchmarks.assess_financial_ratio(
            field, own, owner_equity=owner_equity
        )
        if rating in ("账务异常", "计算失效"):
            skipped.append(label)
            continue
        if own == 0.0:
            continue
        labels.append(label)
        own_vals.append(own * 100)
        bench_vals.append(float(getattr(bench, bfield) or 0) * 100)
    if not labels:
        return None
    out: dict[str, Any] = {
        "type": "bar",
        "data": {
            "labels": labels,
            "series": [
                {"name": "行业均值", "values": bench_vals},
                {"name": "本样本", "values": own_vals},
            ],
        },
    }
    if skipped:
        out["excluded_anomalous"] = skipped
    return out


def _benchmark_interpretation(
    fin: EnterpriseFinancials | None, has_fin: bool, bench: IndustryBenchmark | None
) -> str:
    """同业对标解读（结论前置）：先给「弱于/优于同业」判断，再挂本样本 vs 行业数值。0=弃权。

    账务异常/计算失效指标不参与对比，附注说明。
    """
    if not has_fin or fin is None or bench is None:
        return ""
    owner_equity = float(getattr(fin, "owner_equity", 0) or 0)
    worse: list[str] = []
    better: list[str] = []
    skipped: list[str] = []
    for field, bfield in _BENCH_PCT_RATIOS:
        own = float(getattr(fin, field) or 0)
        label = financial_benchmarks.FINANCIAL_RATIOS[field]["label"]
        rating = financial_benchmarks.assess_financial_ratio(
            field, own, owner_equity=owner_equity
        )
        if rating in ("账务异常", "计算失效"):
            skipped.append(label)
            continue
        if own == 0.0:
            continue
        bval = float(getattr(bench, bfield) or 0)
        if bval <= 0:
            continue
        own_pct, bval_pct = own * 100, bval * 100
        gap = own_pct - bval_pct
        is_debt = field == "debt_ratio"  # 负债率越高越差；其余比率越高越好
        if (is_debt and gap > 5) or ((not is_debt) and gap < -5):
            worse.append(f"{label} {own_pct:.1f}%（行业 {bval_pct:.1f}%）")
        elif (is_debt and gap < -5) or ((not is_debt) and gap > 5):
            better.append(f"{label} {own_pct:.1f}%（行业 {bval_pct:.1f}%）")
    parts: list[str] = []
    if worse and better:
        parts.append(f"弱于同业：{'；'.join(worse[:3])}；优于同业：{'；'.join(better[:3])}。")
    elif worse:
        parts.append(f"弱于同业：{'；'.join(worse[:3])}。")
    elif better:
        parts.append(f"优于同业：{'；'.join(better[:3])}。")
    if skipped:
        parts.append(
            f"「{'、'.join(skipped)}」因账务异常或权益为负计算失效，已排除出同业对标图，须先核原始报表后再对比。"
        )
    return "".join(parts)


def _radar_interpretation(profile: dict[str, Any], dims: list[str] | None = None) -> str:
    """六维风险画像解读：仅对雷达已展示维度发言（与图表对齐）。0=弃权。"""
    from app.services.assessment_weights import DIMENSION_LABELS

    scores = profile.get("dimensions") or {}
    scored = []
    for k, v in scores.items():
        if dims is not None and k not in dims:
            continue
        if isinstance(v, (int, float)) and float(v) > 0:
            scored.append((DIMENSION_LABELS.get(k, k), float(v)))
    if len(scored) < 2:
        return ""
    weakest = min(scored, key=lambda t: t[1])
    strongest = max(scored, key=lambda t: t[1])
    if weakest[0] == strongest[0]:
        return ""
    return (
        f"六维中最弱为「{weakest[0]}」（本维指数 {weakest[1]:.1f}），是主要风险来源；"
        f"「{strongest[0]}」（本维指数 {strongest[1]:.1f}）相对稳健。"
    )


def _apply_temporal_gate(context: dict[str, Any]) -> None:
    """单期数据禁止时序词：剥离 narration/story/claims/risk 面中的持续/逐年/不断（持续经营除外）。"""
    period = int(context.get("period_count") or 1)
    if period >= 2:
        return

    def _scrub(text: str) -> str:
        return hallucination_guard.scrub_temporal_words(text or "")

    if context.get("story"):
        context["story"] = _scrub(context["story"])
    if context.get("executive_summary"):
        context["executive_summary"] = _scrub(context["executive_summary"])
    overall = context.get("overall")
    if isinstance(overall, dict):
        for k in ("reason", "radar_interpretation"):
            if overall.get(k):
                overall[k] = _scrub(str(overall[k]))
        for list_key in ("risk_points", "advantages", "advice"):
            items = overall.get(list_key)
            if isinstance(items, list):
                overall[list_key] = [_scrub(str(x)) for x in items]
    for ch in context.get("chapters") or []:
        if ch.get("narration"):
            ch["narration"] = _scrub(ch["narration"])
        for c in ch.get("claims") or []:
            if isinstance(c, dict) and c.get("claim"):
                c["claim"] = _scrub(c["claim"])
    for block in (context.get("summary_conclusion"),):
        if isinstance(block, str) and block:
            context["summary_conclusion"] = _scrub(block)
    for list_key in ("summary_strengths", "summary_risks"):
        items = context.get(list_key)
        if isinstance(items, list):
            context[list_key] = [_scrub(str(x)) for x in items]


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
        owner_equity = float(getattr(fin, "owner_equity", 0) or 0)
        if owner_equity < 0:
            points.append(
                f"所有者权益 {_fmt_wan(owner_equity)} 万元【资不抵债】，权益类比率不予采信"
            )
        for field, cfg in financial_benchmarks.FINANCIAL_RATIOS.items():
            if cfg.get("warn_dir") is None:
                continue  # roa/asset_turnover/profit_yoy 仅展示不评级，不参与风险锚点
            raw = float(getattr(fin, field) or 0)
            rating = financial_benchmarks.assess_financial_ratio(
                field, raw, owner_equity=owner_equity
            )
            if rating == "计算失效":
                points.append(
                    f"{cfg['label']}【计算失效，权益为负，不予采信】"
                )
                continue
            if raw == 0:
                continue
            if rating == "账务异常":
                points.append(
                    f"{cfg['label']} {financial_benchmarks.format_financial_ratio(field, raw, owner_equity=owner_equity)}【账务异常】"
                )
            elif rating == "预警":
                std = _threshold_text(cfg) or "—"
                points.append(
                    f"{cfg['label']} {financial_benchmarks.format_financial_ratio(field, raw, owner_equity=owner_equity)}"
                    f"（阈值{std}，预警）"
                )
        for label, col in (
            ("负债合计", "total_liab"),
            ("流动负债合计", "current_liab"),
        ):
            raw = float(getattr(fin, col) or 0)
            if financial_benchmarks.is_anomalous_amount(col, raw):
                points.append(f"{label} {_fmt_wan(raw)} 万元【账务异常】")
    for s in signals[:3]:
        points.append(f"预警信号：{judgment_service.WARNING_SIGNAL_LABELS.get(s, s)}")
    return _finalize_summary_bullets(points, limit=8)


# 纳税信用等级里视为「优势」的档位（A/B 为良好；M 新设、C/D 较差，不作为优势挂出）
_GOOD_CREDIT_LEVELS = {"A", "B"}


def _finalize_summary_bullets(items: list[str], *, limit: int) -> list[str]:
    """首页摘要条：完整保留原文，禁止中间截断；仅做去重与条数上限。"""
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        t = str(raw or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)  # 绝不 text[:N] 截断；排版层负责换行
        if len(out) >= limit:
            break
    return out


# 可评级但不作为「主要优势」：同比未跌破预警线 ≠ 经营亮点（避免「营收同比 -5.9%，达标」进优势）
_ADVANTAGE_EXCLUDE_FIELDS = frozenset({"revenue_yoy", "profit_yoy"})


def _collect_advantages(profile: dict[str, Any], fin: EnterpriseFinancials | None) -> list[str]:
    """优势采集（数据锚点化）：每条必须挂具体数值，无值/非良好档位弃权不展示。

    来源：财务四能力「达标」比率（挂数值）→ 纳税信用等级（A/B 才挂）→ 纳税准时率（≥90% 才挂）。
    权益为负时 ROE 等计算失效，禁止纳入优势；同比类不进优势。
    """
    adv: list[str] = []
    if fin is not None:
        owner_equity = float(getattr(fin, "owner_equity", 0) or 0)
        for field, cfg in financial_benchmarks.FINANCIAL_RATIOS.items():
            if cfg.get("warn_dir") is None:
                continue  # 纯展示项（roa/asset_turnover）无评级方向，不进优势
            if field in _ADVANTAGE_EXCLUDE_FIELDS:
                continue
            raw = float(getattr(fin, field) or 0)
            rating = financial_benchmarks.assess_financial_ratio(
                field, raw, owner_equity=owner_equity
            )
            if rating != "达标":
                continue
            std = _threshold_text(cfg)
            fmt = financial_benchmarks.format_financial_ratio(
                field, raw, owner_equity=owner_equity
            )
            if std:
                adv.append(f"{cfg['label']} {fmt}（阈值{std}，达标）")
            else:
                adv.append(f"{cfg['label']} {fmt}，达标")
    credit = str(profile.get("credit_level") or "").strip()
    if credit in _GOOD_CREDIT_LEVELS:
        adv.append(f"纳税信用等级 {credit}")
    on_time = profile.get("tax_on_time_rate")
    if on_time is not None and float(on_time) >= 0.9:
        adv.append(f"纳税准时率 {float(on_time) * 100:.1f}%")
    return _finalize_summary_bullets(adv, limit=6)


def _collect_advice(insights: list[Any]) -> list[str]:
    """章节详版建议（完整保留）。"""
    out: list[str] = []
    for ins in insights:
        if ins.advice and ins.advice not in out:
            out.append(ins.advice)
    return _finalize_summary_bullets(out, limit=6)


def _shorten_advice_line(text: str, *, max_len: int = 48) -> str:
    """首页摘要建议：取首句或截断为精简版，避免与分维章节大段复制。"""
    t = re.sub(r"\s+", "", str(text or "").strip())
    if not t:
        return ""
    # 按句号/分号取首句
    for sep in ("。", "；", ";", "！", "!"):
        if sep in t:
            head = t.split(sep, 1)[0].strip()
            if head:
                t = head + ("。" if sep in ("。", "！", "!") else "")
                break
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _collect_summary_advice(insights: list[Any]) -> list[str]:
    """首页「主要建议」精简版；分维度章节仍用 _collect_advice 详版。"""
    full = _collect_advice(insights)
    short = [_shorten_advice_line(x) for x in full]
    return _finalize_summary_bullets([s for s in short if s], limit=5)


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
    label = profile.get("display_label") or profile.get("enterprise_name") or "样本"
    name = profile.get("display_name") or profile.get("enterprise_name") or label
    short_id = enterprise_id[:8]
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
    risk_points = _collect_risk_points(insights, signals, fin if has_fin else None)
    advantages = _collect_advantages(profile, fin if has_fin else None)
    advice = _collect_summary_advice(insights)

    # ── 分维度风险分析：六维（与雷达同源）+ 财务能力明细 ──
    # 报表内嵌同比字段（revenue_yoy/profit_yoy）≠ 系统多期快照；有同比值则允许解读，禁止「无法同比」矛盾文案
    has_yoy = bool(
        has_fin
        and fin is not None
        and (
            float(getattr(fin, "revenue_yoy", 0) or 0) != 0.0
            or float(getattr(fin, "profit_yoy", 0) or 0) != 0.0
        )
    )
    six_dimensions = _build_six_dim_sections(profile, insights, has_yoy=has_yoy)
    six_dim_temporal_note = _six_dim_temporal_note(has_yoy=has_yoy)
    dimensions = _build_dimension_sections(fin if has_fin else None, has_fin)

    # 命中风险指标：已检指标中评级为预警/异常/失效者 + 摘要风险点（去重计数以指标+风险点合计）
    _HIT_RATINGS = frozenset({"预警", "账务异常", "计算失效", "资不抵债", "高"})
    _SKIP_RATINGS = frozenset({"", "—", "【暂无可用数据】", "暂无可用数据"})
    hit_risk_count = 0
    checked_metric_count = 0
    for sec in (*six_dimensions, *dimensions):
        for m in sec.get("metrics") or []:
            rating = str(m.get("rating") or "").strip()
            if rating in _SKIP_RATINGS:
                continue
            checked_metric_count += 1
            if rating in _HIT_RATINGS:
                hit_risk_count += 1
    # 风险点中非财务比率类信号也计入「命中」（与摘要列表对齐）
    hit_risk_count = max(hit_risk_count, len(risk_points))

    # ── 评级摘要成段理由（结论前置：先给评级判断，再点最弱六维与动作） ──
    weak_dims = [d for d in six_dimensions if d["risk_level"] == "高"]
    if not weak_dims:
        weak_dims = [d for d in dimensions if d["risk_level"] == "高"]
    if weak_dims:
        lead = "、".join(d["title"] for d in weak_dims[:2])
        reason = (
            f"综合评级「{risk_level}」，命中风险指标 {hit_risk_count} 项"
            f"（已检 {checked_metric_count} 项）："
            f"{lead}承压，是主要风险来源，建议优先核查。"
        )
    else:
        reason = (
            f"综合评级「{risk_level}」，命中风险指标 {hit_risk_count} 项"
            f"（已检 {checked_metric_count} 项），整体财务状况「{health}」。"
        )

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
        if render_bar_chart_png(benchmark_chart, p, title="同业对标（本样本 对比 行业均值，%）"):
            benchmark_chart_path = str(p)

    # ── 六维风险画像（雷达 ⊆ 六维正文章节，方案 A 裁剪） ──
    radar_chart_path: str | None = None
    radar_dims = [d["key"] for d in six_dimensions]
    if report_id and radar_dims:
        radar = enterprise_radar_chart(profile, dims=radar_dims)
        if radar:
            chart_dir = REPORTS_DIR / "_charts" / report_id
            chart_dir.mkdir(parents=True, exist_ok=True)
            p = chart_dir / "radar.png"
            if render_radar_chart_png(radar, p, title="六维风险画像"):
                radar_chart_path = str(p)

    total_claims = (
        len(risk_points)
        + sum(len(d["metrics"]) for d in dimensions)
        + sum(len(d.get("metrics") or []) for d in six_dimensions)
    )
    claim_chapters = _enterprise_chapters_for_validation(
        dimensions=[*six_dimensions, *dimensions],
        risk_points=risk_points,
        reason=reason,
        overall_score=profile.get("overall_score"),
    )
    validation = hallucination_guard.validate_report_chapters(claim_chapters)
    # 保留 total_claims 便于封面/前端统计；ok 以真校验为准，禁止占位假 ok
    validation = {**validation, "total_claims": max(validation.get("total_claims") or 0, total_claims)}

    # A.1：封面导语唯一来自 document plan（claim），禁止营销罐装句
    story = compose_story_from_chapters(claim_chapters)
    score = profile.get("overall_score")
    # 封面 KPI 带 metric+source → 跨面机检视为可溯源；评分数字须落在 claim 锚点或溯源卡
    summary_kpis: list[dict[str, Any]] = [
        {
            "label": "风险等级",
            "value": risk_level or "—",
            "unit": "",
            "metric": "risk_level",
            "source": "scoring_layer",
        },
        {
            "label": "命中风险指标",
            "value": str(hit_risk_count),
            "unit": f"/ {checked_metric_count} 项",
            "metric": "hit_risk_count",
            "source": "assessment",
        },
    ]
    executive_summary = reason
    summary_kpis, story, executive_summary, cross_enf = hallucination_guard.enforce_cross_surface(
        chapters=claim_chapters,
        summary_kpis=summary_kpis,
        story=story,
        executive_summary=executive_summary,
    )
    cross_validation = hallucination_guard.validate_cross_surface(
        chapters=claim_chapters,
        summary_kpis=summary_kpis,
        story=story,
        executive_summary=executive_summary,
    )
    validation["cross_enforced"] = cross_enf
    validation["cross_surface"] = cross_validation
    if not cross_validation.get("ok"):
        validation["ok"] = False
    reason = executive_summary

    report_year = fin.report_year if has_fin and getattr(fin, "report_year", None) else None

    context = {
        "scenario": "enterprise",
        "scenario_label": "企业财务分析报告",
        "tier": "general",
        "title": f"企业财务分析报告 · {name}",
        "story": story,
        "summary_kpis": summary_kpis,
        "executive_summary": executive_summary,
        "report_date": _now_cn().strftime("%Y年%m月%d日"),
        "subject": {
            "name": name,
            "short_id": short_id,
            "label": label,
            "industry_l1": zh_industry(profile.get("industry_l1")),
            "industry_l2": profile.get("industry_l2") or None,
            "province": profile.get("province") or None,
            "report_year": report_year,
        },
        "overall": {
            "health": health,
            "health_color": health_color,
            "risk_level": risk_level,
            "outlook": outlook_result["outlook"],
            "outlook_color": outlook_result["color"],
            "overall_score": profile["overall_score"],
            "hit_risk_count": hit_risk_count,
            "checked_metric_count": checked_metric_count,
            "reason": reason,
            "risk_points": risk_points,
            "advantages": advantages,
            "advice": advice,
            "benchmark_groups": bench.get("groups") if bench else None,
            "radar_interpretation": _radar_interpretation(profile, dims=radar_dims),
        },
        "six_dimensions": six_dimensions,
        "six_dim_temporal_note": six_dim_temporal_note,
        "dimensions": dimensions,
        "statements": statements,
        "dupont": dupont,
        "benchmark_chart": benchmark_chart_path,
        "benchmark_interpretation": _benchmark_interpretation(fin, has_fin, industry_bench),
        "radar_chart": radar_chart_path,
        "radar_dims": radar_dims,
        "period_count": 1,  # 当前个体路径仅单期；≥2 期才允许时序词
        "validation": validation,
    }
    # 时序词硬约束（单期禁止「持续/逐年/不断」）
    _apply_temporal_gate(context)
    lexicon = hallucination_guard.validate_surface_lexicon(context, report_kind="enterprise")
    validation["lexicon"] = lexicon
    radar_check = hallucination_guard.validate_radar_subset_of_chapters(
        radar_dims=radar_dims,
        chapter_dim_keys=[d["key"] for d in six_dimensions],
    )
    validation["radar_subset"] = radar_check
    if not lexicon.get("ok") or not radar_check.get("ok"):
        validation["ok"] = False
    return context


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
    _assert_report_renderable(context)
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
