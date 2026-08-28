"""报告图表渲染"""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.report_charts import render_bar_chart_png, render_dimension_attribution_png


def test_render_bar_chart_png(tmp_path):
    chart = {
        "type": "bar",
        "data": {
            "labels": ["制造", "批发"],
            "series": [{"name": "同比%", "values": [5.2, -1.1]}],
        },
    }
    out = tmp_path / "t.png"
    assert render_bar_chart_png(chart, out, title="测试") is True
    assert out.exists()
    assert out.stat().st_size > 100


def test_render_bar_chart_multi_series(tmp_path):
    from app.services.report_charts import render_bar_chart_png

    chart = {
        "type": "bar",
        "data": {
            "labels": ["制造", "批发"],
            "series": [
                {"name": "基准", "values": [70, 65]},
                {"name": "样本", "values": [68, 72]},
            ],
        },
    }
    out = tmp_path / "multi.png"
    assert render_bar_chart_png(chart, out) is True


def test_render_dimension_attribution_png(tmp_path):
    attribution = {
        "dimensions": {
            "tax_health": {"label": "税务健康", "score": 55, "weight": 0.25, "net_contribution": 13.75},
            "authenticity": {"label": "经营真实性", "score": 40, "weight": 0.25, "net_contribution": 10.0},
            "industry": {"label": "行业地位", "score": 60, "weight": 0.20, "net_contribution": 12.0},
            "legal": {"label": "法律合规", "score": 70, "weight": 0.15, "net_contribution": 10.5},
            "finance": {"label": "财务健康", "score": 45, "weight": 0.15, "net_contribution": 6.75},
        }
    }
    out = tmp_path / "attr.png"
    assert render_dimension_attribution_png(attribution, out) is True
    assert out.exists()


def test_render_radar_chart_png(tmp_path):
    from app.services.report_charts import render_radar_chart_png

    chart = {
        "type": "radar",
        "data": {
            "indicators": [
                {"name": "税务", "max": 100},
                {"name": "真实", "max": 100},
            ],
            "values": [60, 55],
            "name": "样本",
        },
    }
    out = tmp_path / "radar.png"
    assert render_radar_chart_png(chart, out, title="雷达") is True
    assert out.stat().st_size > 100


def test_render_heatmap_chart_png(tmp_path):
    from app.services.report_charts import render_heatmap_chart_png

    chart = {
        "type": "heatmap",
        "data": {
            "x_labels": ["A", "B"],
            "y_labels": ["制造", "服务"],
            "values": [[0, 0, 2], [1, 1, 1]],
        },
    }
    out = tmp_path / "heat.png"
    assert render_heatmap_chart_png(chart, out) is True
    assert out.exists()


def test_render_funnel_chart_png(tmp_path):
    from app.services.report_charts import render_funnel_chart_png

    chart = {
        "type": "funnel",
        "data": {
            "labels": ["全样本", "命中信号", "税务违法"],
            "values": [100, 40, 10],
        },
    }
    out = tmp_path / "funnel.png"
    assert render_funnel_chart_png(chart, out) is True
    assert out.exists()
