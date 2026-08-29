"""路线 B：Jinja2 HTML 模板 + WeasyPrint → PDF（图表预渲染 PNG 以 base64 嵌入）。"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


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
    out["attribution_dimensions"] = list(dims.values())

    val = context.get("validation") or {}
    out["validation_ok"] = bool(val.get("ok"))
    out["validation_detail"] = (
        f"claims={val.get('total_claims', 0)}, unanchored={val.get('unanchored', 0)}"
    )
    tier = context.get("tier") or "general"
    out["tier_label"] = "付费定制" if tier == "premium" else "通用模板"
    # 五场景封面元数据兜底（历史 fixture 无 cover/subtitle 也能渲染）
    out["cover"] = context.get("cover") or {"motif": "compass", "accent": "#003366"}
    out["subtitle"] = context.get("subtitle") or ""
    out["data_focus"] = list(context.get("data_focus") or [])
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
        html = build_report_html(context, report_id)
        generate_pdf_weasyprint(html, output_path)
        return output_path.exists() and output_path.stat().st_size > 500
    except Exception as exc:
        logger.warning("WeasyPrint PDF failed, fallback to FPDF: %s", exc)
        return False
