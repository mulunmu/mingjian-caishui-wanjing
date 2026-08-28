"""报告 HTML 结构快照 — 锁定 WeasyPrint 模板关键区块（非像素级）"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.report_html import build_report_html


def _full_context():
    return {
        "scenario": "general",
        "scenario_label": "行业趋势风控",
        "tier": "standard",
        "title": "行业趋势风控报告",
        "story": "面向通识读者，讲清样本覆盖、行业走向与主要风险信号。",
        "report_date": "2026年08月27日",
        "summary_kpis": [
            {"label": "样本规模", "value": "193", "unit": "家"},
            {"label": "综合均分", "value": "47.0", "unit": "分"},
            {"label": "关注行业", "value": "制造", "unit": ""},
        ],
        "chapters": [
            {
                "title": "五维雷达 · 综合画像",
                "purpose": "样本五维均分雷达",
                "claims": [{"claim": "全样本综合均分47.0分。", "confidence": "computed", "trace": {}, "evidence_chain": []}],
                "numeric_rows": [["avg_score", "47.0", "分", "综合均分"]],
                "chart_data_uri": "data:image/png;base64,iVBORw0KGgo=",
            },
            {
                "title": "行业趋势",
                "purpose": "各行业营收同比",
                "claims": [{"claim": "制造行业同比 5%。", "confidence": "computed", "trace": {}, "evidence_chain": []}],
                "numeric_rows": [["avg_revenue_yoy", "5.2", "%", "制造同比"]],
                "chart_data_uri": None,
            },
        ],
        "attribution": {
            "summary": "全样本（193家）综合均分47.0分，税务违法拖累明显。",
            "drag_factors": [{"item": "税务违法", "count": 12}],
            "dimensions": {
                "tax_health": {"label": "税务健康", "score": 55, "weight": 0.25, "net_contribution": 13.75},
                "legal": {"label": "法律合规", "score": 70, "weight": 0.05, "net_contribution": 3.5},
            },
        },
        "attribution_chart_data_uri": "data:image/png;base64,iVBORw0KGgo=",
        "validation": {"ok": True, "total_claims": 6, "unanchored": 0},
        "appendix": {
            "data": ["core_metrics", "syx_tax_illega", "syx_auditing"],
            "methods": ["趋势聚合", "Benford", "互斥分桶预警"],
        },
    }


REQUIRED_MARKERS = [
    "行业趋势风控报告",
    "样本规模",
    "五维雷达 · 综合画像",
    "维度归因",
    "主要拖累因素",
    "抗幻觉",
    "附录",
    "core_metrics",
]


def test_report_html_structure_snapshot(tmp_path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")
    ctx = _full_context()
    ctx.pop("attribution_chart_data_uri", None)
    ctx["attribution_chart"] = str(chart_path)
    ctx["chapters"][0].pop("chart_data_uri", None)
    ctx["chapters"][0]["chart_image"] = str(chart_path)
    html = build_report_html(ctx, "slice_general_structure_test")
    for marker in REQUIRED_MARKERS:
        assert marker in html, f"missing section marker: {marker}"
    assert "data:image/png;base64," in html
    assert html.count("<table") >= 2
