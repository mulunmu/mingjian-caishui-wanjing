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

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.claim import Claim, ClaimTrace, ClaimValue, filter_claims
from app.services import conclusion_store, hallucination_guard, judgment_service, llm_reply
from app.services import assessment
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
    get_scenario,
    get_scenario_label,
    get_scenario_tier,
    is_premium_locked,
    resolve_scenario,
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


def write_report_meta(report_id: str, *, owner: str | None = None, kind: str = "slice") -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "report_id": report_id,
        "owner": owner,
        "kind": kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
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

    intent = IntentResult(function=function, dimension=dimension, intent=f"{function}_{dimension}")
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


def _build_summary_kpis(chapters: list[dict[str, Any]]) -> list[dict[str, str]]:
    """封面关键指标卡：从各章 meta / claims 聚合。"""
    sample_n = 0
    high_risk_n = 0
    avg_score: float | None = None
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
            if m == "avg_credit_score" and n is not None:
                avg_score = float(n)
            if m == "avg_composite" and n is not None and avg_score is None:
                avg_score = float(n)

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
        {"label": "综合均分", "value": f"{avg_score:.1f}" if avg_score is not None else "—", "unit": "分"},
        {"label": "关注行业", "value": top_industry, "unit": ""},
    ]
    return kpis


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
        ctype = chart.get("type")
        if ctype == "line":
            ok = render_line_chart_png(chart, path, title=ch.get("title") or "")
        elif ctype == "pie":
            ok = render_pie_chart_png(chart, path, title=ch.get("title") or "")
        elif ctype == "radar":
            ok = render_radar_chart_png(chart, path, title=ch.get("title") or "")
        elif ctype == "heatmap":
            ok = render_heatmap_chart_png(chart, path, title=ch.get("title") or "")
        elif ctype == "funnel":
            ok = render_funnel_chart_png(chart, path, title=ch.get("title") or "")
        else:
            ok = render_bar_chart_png(chart, path, title=ch.get("title") or "")
        ch["chart_image"] = str(path) if ok else None


async def build_slice_report_context(
    db: AsyncSession,
    *,
    scenario: str = "general",
    session_id: str | None = None,
    query: str | None = None,
    report_id: str | None = None,
) -> dict[str, Any]:
    key = resolve_scenario(query=query, scenario=scenario)
    if get_scenario_tier(key) == "premium" and is_premium_locked():
        raise PremiumReportLocked(key)
    spec = get_scenario(key)
    chapters = []
    chapter_claims: list[list[Claim]] = []

    try:
        attribution = await assessment.get_slice_attribution(db)
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
                    table="core_metrics",
                    field="credit_score",
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
                "title": "五维雷达 · 综合画像",
                "purpose": "样本五维均分雷达与综合均分",
                "function": "score",
                "dimension": "overall",
                "claims": ctx_radar,
                "meta": {"attribution": attribution},
                "charts": radar_chart,
                "numeric_rows": _numeric_table_rows(ctx_radar),
            }
        )

    for ch in spec["chapters"]:
        claims, meta = await _chapter_claims(db, session_id, ch["function"], ch["dimension"])
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
            }
        )

    if report_id:
        chart_dir = REPORTS_DIR / "_charts" / report_id
        _render_chapter_charts(chapters, chart_dir)

    # 章节解读：LLM 锚定结论生成（失败则无解读，不影响报告可用性）
    if llm_reply.is_llm_configured():
        narrations = await asyncio.gather(
            *(
                llm_reply.generate_narration(ch["title"], safe)
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
    summary_kpis = _build_summary_kpis(chapters)
    executive_summary = _fallback_executive_summary(summary_kpis, chapters)
    if llm_reply.is_llm_configured():
        try:
            flat_claims: list[Claim] = [c for cc in chapter_claims for c in cc]
            s = await llm_reply.generate_executive_summary(
                kpis=summary_kpis,
                chapter_titles=[ch["title"] for ch in chapters],
                claims=flat_claims,
            )
            if s:
                executive_summary = s
        except Exception as exc:
            logger.warning("executive summary LLM failed: %s", exc)
    return {
        "scenario": key,
        "scenario_label": get_scenario_label(key),
        "tier": get_scenario_tier(key),
        "title": spec["title"],
        "story": spec["story"],
        "report_date": _now_cn().strftime("%Y年%m月%d日"),
        "chapters": chapters,
        "summary_kpis": summary_kpis,
        "executive_summary": executive_summary,
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
                "归因：五维加权贡献 + 高频拖累因素（样本聚合）",
                "渲染：Jinja2 + WeasyPrint（HTML→PDF，FPDF 降级）",
            ],
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

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    font_path = _font_path()
    if font_path:
        pdf.add_font("CN", "", str(font_path))
        fn = "CN"
    else:
        fn = "Helvetica"

    # 封面
    pdf.add_page()
    _para(pdf, context["title"], size=18, h=10, align="C")
    pdf.ln(6)
    _para(pdf, context["story"], size=12, h=7, align="C")
    pdf.ln(8)

    kpis = context.get("summary_kpis") or []
    if kpis:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=12)
        pdf.cell(_text_w(pdf), 8, "关键指标", ln=True)
        col_w = _text_w(pdf) / max(len(kpis), 1)
        pdf.set_font(fn, size=10)
        for k in kpis:
            pdf.cell(col_w, 7, k["label"], border=1, align="C")
        pdf.ln()
        for k in kpis:
            pdf.cell(col_w, 10, f"{k['value']}{k['unit']}", border=1, align="C")
        pdf.ln(10)

    tier_txt = "付费定制" if context.get("tier") == "premium" else "通用模板"
    for line in (
        f"报告日期：{context['report_date']}",
        f"报告编号：{report_id}",
        f"场景：{context.get('scenario_label', context['scenario'])}",
        f"报告层级：{tier_txt}",
    ):
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=11)
        pdf.cell(_text_w(pdf), 8, line, ln=True, align="C")
    val = context.get("validation") or {}
    pdf.set_x(pdf.l_margin)
    pdf.set_font(fn, size=11)
    pdf.cell(
        _text_w(pdf),
        8,
        f"抗幻觉校验：{'通过' if val.get('ok') else '有告警'}（claims={val.get('total_claims')}, unanchored={val.get('unanchored')}）",
        ln=True,
        align="C",
    )

    # 执行摘要
    exec_summary = context.get("executive_summary")
    if exec_summary:
        pdf.add_page()
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, "执行摘要", ln=True)
        _para(pdf, exec_summary, size=11, h=6)
        pdf.ln(3)

    # 归因章节
    attr = context.get("attribution") or {}
    if attr.get("summary"):
        pdf.add_page()
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
            pdf.cell(_text_w(pdf), 8, "五维加权贡献", ln=True)
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
            headers = ["维度", "得分", "权重", "加权贡献"]
            col_w = _text_w(pdf) / len(headers)
            pdf.set_font(fn, size=10)
            for h in headers:
                pdf.cell(col_w, 7, h, border=1, align="C")
            pdf.ln()
            for d in dims.values():
                pdf.cell(col_w, 6, str(d.get("label", ""))[:12], border=1)
                pdf.cell(col_w, 6, f"{d.get('score', 0):.1f}", border=1, align="C")
                pdf.cell(col_w, 6, f"{float(d.get('weight', 0)) * 100:.0f}%", border=1, align="C")
                pdf.cell(col_w, 6, f"{d.get('net_contribution', 0):.1f}", border=1, align="C")
                pdf.ln()
            pdf.ln(3)

    # 章节
    for i, ch in enumerate(context["chapters"], 1):
        pdf.add_page()
        pdf.set_x(pdf.l_margin)
        pdf.set_font(fn, size=14)
        pdf.cell(_text_w(pdf), 10, f"{i}. {ch['title']}", ln=True)
        _para(pdf, f"功能说明：{ch['purpose']}", size=11, h=6)
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
            headers = ["指标", "数值", "单位", "说明摘要"]
            col_w = _text_w(pdf) / len(headers)
            pdf.set_font(fn, size=10)
            for h in headers:
                pdf.cell(col_w, 7, h, border=1, align="C")
            pdf.ln()
            for row in num_rows[:12]:
                for cell in row:
                    pdf.cell(col_w, 6, str(cell)[:24], border=1)
                pdf.ln()
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
) -> tuple[str, Path, dict[str, Any]]:
    cleanup_legacy_reports()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    key = resolve_scenario(query=query, scenario=scenario)
    report_id = _new_report_id("slice", key)
    output_path = REPORTS_DIR / f"{report_id}.pdf"

    context = await build_slice_report_context(
        db, scenario=key, session_id=session_id, query=query, report_id=report_id
    )
    if not context.get("chapters") or int(
        (context.get("attribution") or {}).get("sample_count") or 0
    ) <= 0:
        raise ValueError("当前切片无有效样本数据，无法生成报告。请先接入并确认数据。")
    _generate_slice_pdf(context, report_id, output_path)
    write_report_meta(report_id, owner=owner, kind="slice")
    return report_id, output_path, context


async def build_enterprise_report_context(
    db: AsyncSession, *, enterprise_id: str, report_id: str | None = None
) -> dict[str, Any]:
    """个体深度报告上下文：画像 + 同业基准 + 风险成因 + 预警信号（脱敏，仅哈希 id）。"""
    from app.services.chart_payloads import enterprise_radar_chart

    profile = await assessment.calculate(db, enterprise_id)
    if not profile:
        raise ValueError("未找到该匿名样本")

    bench = await assessment.peer_benchmark(db, enterprise_id)
    label = profile.get("display_label") or profile.get("enterprise_name")
    short_id = enterprise_id[:8]

    chapters: list[dict[str, Any]] = []
    chapter_claims: list[list[Claim]] = []

    def _c(
        text: str,
        *,
        metric: str,
        number: float | int | None = None,
        unit: str = "",
        table: str = "core_metrics",
        field: str = "credit_score",
        query_id: str,
        confidence: str = "computed",
        evidence: list[str] | None = None,
    ) -> Claim:
        return Claim(
            claim=text,
            value=ClaimValue(metric=metric, number=number, unit=unit) if number is not None else None,
            trace=ClaimTrace(table=table, field=field, query_id=query_id),
            confidence=confidence,  # type: ignore[arg-type]
            evidence_chain=evidence or [],
        )

    # ① 个体画像（overall + 五维 + 雷达）
    overview_claims = [
        _c(
            f"匿名样本 #{short_id}（{label}）综合评分 {profile['overall_score']} 分，"
            f"风险等级 {profile['risk_level']}。",
            metric="overall_score",
            number=profile["overall_score"],
            unit="分",
            query_id="Q_ent_report_overall",
            evidence=[
                f"industry={profile.get('industry_l1')}",
                f"province={profile.get('province')}",
            ],
        )
    ]
    dims = profile.get("dimensions") or {}
    dim_details = profile.get("dimension_details") or {}
    for key in ("tax_health", "authenticity", "industry", "legal", "finance"):
        if dims.get(key) is None:
            continue
        d = dim_details.get(key) or {}
        overview_claims.append(
            _c(
                f"{d.get('label', key)}维度 {float(dims[key]):.1f} 分"
                f"（权重 {float(d.get('weight', 0)) * 100:.0f}%）。",
                metric=f"dim_{key}",
                number=round(float(dims[key]), 2),
                unit="分",
                query_id=f"Q_ent_report_dim_{key}",
                evidence=[f"weight={d.get('weight')}"],
            )
        )
    radar = enterprise_radar_chart(profile)
    ctx_overview = _claims_to_ctx(overview_claims)
    chapters.append(
        {
            "title": "个体画像",
            "purpose": "综合评分、风险等级与五维得分雷达",
            "function": "enterprise",
            "dimension": "overall",
            "claims": ctx_overview,
            "meta": {
                "overall_score": profile["overall_score"],
                "risk_level": profile["risk_level"],
                "industry_l1": profile.get("industry_l1"),
                "province": profile.get("province"),
            },
            "charts": radar,
            "numeric_rows": _numeric_table_rows(ctx_overview),
        }
    )
    chapter_claims.append(overview_claims)

    # ② 同业基准定位
    benchmark_claims: list[Claim] = []
    if bench:
        groups = bench.get("groups") or {}
        for gkey in ("industry", "province", "scale"):
            g = groups.get(gkey)
            if not g:
                continue
            benchmark_claims.append(
                _c(
                    f"{g['label']}（{g['value']}）排名第 {g['rank']}/{g['peer_total']}，"
                    f"位于 {g['percentile']} 分位，偏离群体均值 {g['deviation']:+} 分。",
                    metric=f"peer_{gkey}_percentile",
                    number=g["percentile"],
                    unit="分位",
                    query_id=f"Q_ent_report_peer_{gkey}",
                    confidence="inferred",
                    evidence=[f"rank={g['rank']}/{g['peer_total']}", f"mean={g['group_mean']}"],
                )
            )
    if benchmark_claims:
        bench_groups = [bench["groups"][gkey] for gkey in ("industry", "province", "scale") if bench.get("groups", {}).get(gkey)]
        benchmark_chart = {
            "type": "bar",
            "data": {
                "labels": [g["label"] for g in bench_groups],
                "series": [
                    {"name": "群体均值", "values": [g["group_mean"] for g in bench_groups]},
                    {"name": "本样本", "values": [g["score"] for g in bench_groups]},
                ],
            },
        }
        ctx_bench = _claims_to_ctx(benchmark_claims)
        chapters.append(
            {
                "title": "同业基准定位",
                "purpose": "在同行业 / 同地区 / 同规模群体中的位置",
                "function": "enterprise",
                "dimension": "benchmark",
                "claims": ctx_bench,
                "meta": {"groups": bench.get("groups")},
                "charts": benchmark_chart,
                "numeric_rows": _numeric_table_rows(ctx_bench),
            }
        )
        chapter_claims.append(benchmark_claims)

    # ③ 风险成因与归因
    attr = profile.get("attribution") or {}
    cause_claims: list[Claim] = []
    for key, d in (attr.get("dimensions") or {}).items():
        for n in d.get("negative") or []:
            tail = f"（扣 {n['deduction']} 分）" if n.get("deduction") else ""
            cause_claims.append(
                _c(
                    f"{d.get('label', key)}：{n['item']}{tail}。",
                    metric="risk_factor",
                    number=n.get("deduction"),
                    unit="分",
                    query_id="Q_ent_report_neg",
                    evidence=[f"dimension={d.get('label', key)}", f"item={n['item']}"],
                )
            )
    if attr.get("summary"):
        cause_claims.append(
            _c(
                attr["summary"],
                metric="overall_score",
                number=profile["overall_score"],
                unit="分",
                query_id="Q_ent_report_attribution",
            )
        )
    if cause_claims:
        ctx_cause = _claims_to_ctx(cause_claims)
        chapters.append(
            {
                "title": "风险成因 · 归因",
                "purpose": "主要拖累因素与维度归因",
                "function": "enterprise",
                "dimension": "attribution",
                "claims": ctx_cause,
                "meta": {"attribution": attr},
                "charts": None,
                "numeric_rows": _numeric_table_rows(ctx_cause),
            }
        )
        chapter_claims.append(cause_claims)

    # ④ 预警信号
    signals = profile.get("warning_signals") or []
    signal_claims: list[Claim] = []
    if signals:
        signal_labels = [judgment_service.WARNING_SIGNAL_LABELS.get(s, s) for s in signals]
        signal_claims.append(
            _c(
                f"预警信号：{'、'.join(signal_labels)}。",
                metric="warning_signal_count",
                number=len(signals),
                unit="项",
                query_id="Q_ent_report_signals",
                confidence="inferred",
                evidence=[f"signals={signals}"],
            )
        )
    if signal_claims:
        ctx_signal = _claims_to_ctx(signal_claims)
        chapters.append(
            {
                "title": "预警信号",
                "purpose": "活跃预警信号清单",
                "function": "enterprise",
                "dimension": "signal",
                "claims": ctx_signal,
                "meta": {"warning_signals": signals},
                "charts": None,
                "numeric_rows": _numeric_table_rows(ctx_signal),
            }
        )
        chapter_claims.append(signal_claims)

    if report_id:
        chart_dir = REPORTS_DIR / "_charts" / report_id
        _render_chapter_charts(chapters, chart_dir)

    # 章节解读（LLM 锚定结论，失败无碍）
    if llm_reply.is_llm_configured():
        narrations = await asyncio.gather(
            *(
                llm_reply.generate_narration(ch["title"], safe)
                for ch, safe in zip(chapters, chapter_claims)
            )
        )
        for ch, narration in zip(chapters, narrations):
            if narration:
                ch["narration"] = narration

    validation = hallucination_guard.validate_report_chapters(chapters)
    summary_kpis = [
        {"label": "综合评分", "value": f"{profile['overall_score']:.1f}", "unit": "分"},
        {"label": "风险等级", "value": profile["risk_level"], "unit": ""},
        {"label": "所属行业", "value": profile.get("industry_l1") or "—", "unit": ""},
        {"label": "预警信号", "value": str(len(signals)), "unit": "项"},
    ]
    executive_summary = (
        f"本报告针对匿名样本 #{short_id}（{label}）进行个体深度风控分析，"
        f"综合评分 {profile['overall_score']:.1f} 分（{profile['risk_level']}）。"
        + (attr.get("summary") or "")
    )
    if llm_reply.is_llm_configured():
        try:
            flat_claims = [c for cc in chapter_claims for c in cc]
            s = await llm_reply.generate_executive_summary(
                kpis=summary_kpis,
                chapter_titles=[ch["title"] for ch in chapters],
                claims=flat_claims,
            )
            if s:
                executive_summary = s
        except Exception as exc:
            logger.warning("enterprise executive summary LLM failed: %s", exc)

    return {
        "scenario": "enterprise",
        "scenario_label": "个体深度风控分析",
        "tier": "general",
        "title": f"个体深度风控报告 · #{short_id}",
        "story": f"针对匿名样本 #{short_id}（{label}）的画像、同业基准、风险成因与预警信号深度风控分析。",
        "report_date": _now_cn().strftime("%Y年%m月%d日"),
        "chapters": chapters,
        "summary_kpis": summary_kpis,
        "executive_summary": executive_summary,
        "attribution": attr,
        "attribution_chart": None,
        "validation": validation,
        "appendix": {
            "data": [
                "core_metrics：匿名税务宽表（PG）",
                "industry_benchmark：行业基准（PG）",
                "法律侧仅覆盖税务违法，不含失信/被执行/诉讼（脱敏）",
            ],
            "methods": [
                "五维加权评分：税务健康/真实性/行业地位/法律合规/财务健康",
                "同业基准：同行业/同地区/同规模三组 overall_score 百分位",
                "归因：五维正向贡献与负向扣分项",
                "抗幻觉：仅保留 computed/inferred；数字须有 trace",
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
    _generate_slice_pdf(context, report_id, output_path)
    write_report_meta(report_id, owner=owner, kind="enterprise")
    return report_id, output_path, context


def get_report_path(report_id: str) -> Path | None:
    if not _SAFE_REPORT_ID.match(report_id):
        return None
    path = (REPORTS_DIR / f"{report_id}.pdf").resolve()
    if not str(path).startswith(str(REPORTS_DIR.resolve())):
        return None
    return path if path.exists() else None
