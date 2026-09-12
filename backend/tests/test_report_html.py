"""WeasyPrint HTML 报告渲染"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.report_html import (
    build_report_html,
    prepare_html_context,
    weasyprint_available,
)


def _sample_context():
    return {
        "scenario": "due_diligence",
        "title": "行业趋势风控报告",
        "story": "面向通识读者，讲清样本覆盖、行业走向与主要风险信号。",
        "report_date": "2026年08月26日",
        "summary_kpis": [
            {"label": "样本规模", "value": "193", "unit": "家"},
            {"label": "综合均分", "value": "47.0", "unit": "分"},
        ],
        "chapters": [
            {
                "title": "行业趋势",
                "purpose": "描述各行业营收同比。",
                "claims": [
                    {
                        "claim": "制造行业同比 5%。",
                        "confidence": "computed",
                        "trace": {"table": "core_metrics", "field": "revenue_yoy", "query_id": "Q1"},
                        "evidence_chain": [],
                    }
                ],
                "numeric_rows": [["avg_revenue_yoy", "5.2", "%", "制造行业同比"]],
                "chart_image": None,
            }
        ],
        "attribution": {
            "summary": "全样本综合均分47.0分。",
            "drag_factors": [{"item": "税务违法", "count": 12}],
            "dimensions": {
                "tax_health": {
                    "label": "税务健康",
                    "score": 55,
                    "weight": 0.25,
                    "net_contribution": 13.75,
                }
            },
        },
        "attribution_chart": None,
        "validation": {"ok": True, "total_claims": 4, "unanchored": 0},
        "appendix": {"data": ["core_metrics"], "methods": ["趋势聚合"]},
    }


def test_build_report_html_contains_title():
    html = build_report_html(_sample_context(), "slice_general_test")
    assert "行业趋势风控报告" in html
    assert "制造行业同比" in html
    assert "税务健康" in html


def test_prepare_html_context_validation():
    ctx = prepare_html_context(_sample_context(), "rid")
    assert ctx["report_id"] == "rid"
    assert ctx["renderer"] == "weasyprint"


def test_weasyprint_smoke(tmp_path):
    if not weasyprint_available():
        return
    from app.services.report_html import generate_pdf_weasyprint

    html = build_report_html(_sample_context(), "slice_test")
    out = tmp_path / "t.pdf"
    generate_pdf_weasyprint(html, out)
    assert out.exists()
    assert out.stat().st_size > 1000
