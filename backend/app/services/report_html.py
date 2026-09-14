"""路线 B：Jinja2 HTML 模板 + WeasyPrint → PDF（图表预渲染 PNG 以 base64 嵌入）。"""
from __future__ import annotations

import base64
import logging
import os
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.report_templates import (
    actionable_advice,
    business_level,
    chapter_conclusion_lines,
    cover_frame_key,
    metric_level,
    zh_report_no,
)

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)
_env.globals["business_level"] = business_level
_env.globals["metric_level"] = metric_level
_env.globals["chapter_conclusion_lines"] = chapter_conclusion_lines
_env.globals["actionable_advice"] = actionable_advice


def _file_to_data_uri(path: str | Path | None, *, mime: str = "image/png") -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    raw = p.read_bytes()
    if not raw:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _first_sentence(text: str | None, *, max_len: int = 72) -> str:
    t = re.sub(r"\s+", "", str(text or "").strip())
    if not t:
        return ""
    for sep in ("。", "！", "？", ";", "；"):
        if sep in t:
            t = t.split(sep, 1)[0].strip() + ("。" if sep in ("。", "！", "？") else "")
            break
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _cover_frame_uri(scenario: str | None) -> str | None:
    frame = cover_frame_key(scenario)
    path = _TEMPLATES_DIR / "assets" / f"cover_frame_{frame}.svg"
    return _file_to_data_uri(path, mime="image/svg+xml")


def prepare_html_context(context: dict[str, Any], report_id: str) -> dict[str, Any]:
    """为模板准备上下文：图表转 data URI，归因维度转列表，封面回纹框。"""
    out = dict(context)
    out["report_id"] = report_id
    out["report_no"] = zh_report_no(report_id)
    out["renderer"] = "weasyprint"

    chapters = []
    for ch in context.get("chapters") or []:
        ch_copy = dict(ch)
        ch_copy["chart_data_uri"] = _file_to_data_uri(ch.get("chart_image"))
        meta = ch.get("meta") or {}
        score = meta.get("avg_score")
        if score is None:
            score = ch.get("score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        if score_f is not None:
            ch_copy["business_level"] = business_level(score_f)
        chapters.append(ch_copy)
    out["chapters"] = chapters

    out["attribution_chart_data_uri"] = _file_to_data_uri(context.get("attribution_chart"))
    out["radar_chart_data_uri"] = _file_to_data_uri(context.get("radar_chart"))
    out["benchmark_chart_data_uri"] = _file_to_data_uri(context.get("benchmark_chart"))
    out["cover_frame_data_uri"] = _cover_frame_uri(context.get("scenario"))

    attr = context.get("attribution") or {}
    dims = attr.get("dimensions") or {}
    _dims = []
    for d in dims.values():
        _d = dict(d)
        score = d.get("score")
        try:
            score_f = float(score) if score is not None else None
        except (TypeError, ValueError):
            score_f = None
        _d["score"] = score_f
        _d["score_disp"] = f"{score_f:.1f}" if score_f is not None else "【暂无可用数据】"
        _d["business_level"] = (
            business_level(score_f) if score_f is not None else "【暂无可用数据】"
        )
        _d["metric_level"] = metric_level(score_f) if score_f is not None else "正常"
        _dims.append(_d)
    out["attribution_dimensions"] = _dims

    sample_n = int(attr.get("sample_count") or 0)
    drag_out = []
    for d in attr.get("drag_factors") or []:
        _f = dict(d)
        try:
            cnt = int(d.get("count") or 0)
        except (TypeError, ValueError):
            cnt = 0
        if sample_n > 0:
            _f["pct_disp"] = f"{min(100.0, round(cnt / sample_n * 100, 1)):.1f}%"
            _f["count_disp"] = f"{cnt} 家 / 样本 {sample_n} 家（{_f['pct_disp']}）"
        else:
            _f["pct_disp"] = ""
            _f["count_disp"] = f"{cnt} 家"
        drag_out.append(_f)
    out["attribution_drag_factors"] = drag_out

    tier = context.get("tier") or "general"
    out["tier_label"] = "付费定制" if tier == "premium" else "通用模板"
    # 封面元数据兜底（历史 fixture 无 cover/subtitle 也能渲染）
    cover = dict(context.get("cover") or {"motif": "compass", "accent": "#152446"})
    if not cover.get("accent"):
        cover["accent"] = "#152446"
    out["cover"] = cover
    out["subtitle"] = context.get("subtitle") or ""
    out["data_focus"] = list(context.get("data_focus") or [])

    subject_obj = context.get("subject") or {}
    cm = dict(
        context.get("cover_meta")
        or {
            "scenario_label": context.get("scenario_label") or "",
            "risk_level": "—",
            "business_level": "—",
            "sample_count": "—",
        }
    )
    if not cm.get("scenario_label"):
        cm["scenario_label"] = context.get("scenario_label") or ""
    if not cm.get("subject"):
        cm["subject"] = (
            context.get("scope")
            or subject_obj.get("name")
            or subject_obj.get("label")
            or "全库样本"
        )
    if not cm.get("one_liner"):
        overall = context.get("overall") or {}
        cm["one_liner"] = _first_sentence(
            cm.get("one_liner")
            or context.get("summary_conclusion")
            or overall.get("reason")
            or context.get("executive_summary")
            or context.get("story")
        )
    else:
        cm["one_liner"] = _first_sentence(cm.get("one_liner"))
    cm.setdefault("frame", cover_frame_key(context.get("scenario")))
    out["cover_meta"] = cm

    # 个体建议 → 可照做动作句（模板可再调 actionable_advice）
    overall = dict(out.get("overall") or {})
    if overall.get("advice") is not None:
        overall["advice"] = actionable_advice(
            list(overall.get("advice") or []),
            scenario=context.get("scenario"),
        )
        out["overall"] = overall
    return out


def build_report_html(context: dict[str, Any], report_id: str) -> str:
    template = (
        "enterprise_report.html"
        if context.get("scenario") == "enterprise"
        else "slice_report.html"
    )
    tpl = _env.get_template(template)
    return tpl.render(**prepare_html_context(context, report_id))


def weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:  # ImportError / OSError（Windows 缺 GTK/pango/cairo 系统库）
        return False


def preferred_renderer() -> str:
    """weasyprint | fpdf，默认 weasyprint（不可用时由 slice_report 降级）。"""
    return os.getenv("REPORT_RENDERER", "weasyprint").strip().lower()


def generate_pdf_weasyprint(html: str, output_path: Path) -> None:
    from weasyprint import HTML

    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf(str(output_path))


def try_generate_weasyprint_pdf(
    context: dict[str, Any],
    report_id: str,
    output_path: Path,
) -> bool:
    if preferred_renderer() == "fpdf":
        return False
    if not weasyprint_available():
        logger.info("WeasyPrint unavailable, falling back to FPDF")
        return False
    try:
        from app.services.report_preflight import run_postflight_html, write_validation_log

        reports_dir = output_path.parent
        html = build_report_html(context, report_id)
        post = run_postflight_html(html, context)
        write_validation_log(
            report_id,
            reports_dir=reports_dir,
            preflight=context.get("preflight"),
            postflight=post,
        )
        if not post.get("ok"):
            # 后置校验失败：禁止写 PDF，也不降级 FPDF（避免脏报告流出）
            raise ValueError(
                "报告 HTML 后置校验未通过，拒绝生成 PDF。"
                f"详情：{(post.get('html') or {}).get('hard')}"
            )
        generate_pdf_weasyprint(html, output_path)
        return output_path.exists() and output_path.stat().st_size > 500
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("WeasyPrint PDF failed, fallback to FPDF: %s", exc)
        return False
