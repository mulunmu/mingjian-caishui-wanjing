"""路线 B：Jinja2 HTML 模板 + WeasyPrint → PDF（图表预渲染 PNG 以 base64 嵌入）。"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.report_templates import business_level, chapter_conclusion_lines, zh_report_no

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)
_env.globals["business_level"] = business_level
_env.globals["chapter_conclusion_lines"] = chapter_conclusion_lines


def _file_to_data_uri(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    raw = p.read_bytes()
    if not raw:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def prepare_html_context(context: dict[str, Any], report_id: str) -> dict[str, Any]:
    """为模板准备上下文：图表转 data URI，归因维度转列表。"""
    out = dict(context)
    out["report_id"] = report_id
    out["report_no"] = zh_report_no(report_id)
    out["renderer"] = "weasyprint"

    chapters = []
    for ch in context.get("chapters") or []:
        ch_copy = dict(ch)
        ch_copy["chart_data_uri"] = _file_to_data_uri(ch.get("chart_image"))
        chapters.append(ch_copy)
    out["chapters"] = chapters

    out["attribution_chart_data_uri"] = _file_to_data_uri(context.get("attribution_chart"))
    out["radar_chart_data_uri"] = _file_to_data_uri(context.get("radar_chart"))
    out["benchmark_chart_data_uri"] = _file_to_data_uri(context.get("benchmark_chart"))

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
    # 五场景封面元数据兜底（历史 fixture 无 cover/subtitle 也能渲染）
    out["cover"] = context.get("cover") or {"motif": "compass", "accent": "#003366"}
    out["subtitle"] = context.get("subtitle") or ""
    out["data_focus"] = list(context.get("data_focus") or [])
    # 封面统一款元数据兜底（场景/风险等级/综合均分/样本规模；历史 fixture 无 cover_meta 也能渲染）
    out["cover_meta"] = context.get("cover_meta") or {
        "scenario_label": context.get("scenario_label") or "",
        "risk_level": "—",
        "business_level": "—",
        "sample_count": "—",
    }
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
