"""chart_payloads 单元测试"""
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_attribution_radar_chart():
    from app.services.chart_payloads import attribution_radar_chart

    attr = {
        "summary": "全样本综合均分47.0分",
        "avg_score": 47.0,
        "dimensions": {
            "tax_health": {"label": "税务健康", "score": 55, "net_contribution": 13.75},
            "authenticity": {"label": "经营真实性", "score": 40, "net_contribution": 10.0},
        },
    }
    chart = attribution_radar_chart(attr)
    assert chart is not None
    assert chart["type"] == "radar"
    assert len(chart["data"]["values"]) == 2


def test_attribution_radar_dims_filter():
    """雷达按章节裁剪：dims 非空时只展示给定维度（铁律：雷达 ⊆ 正文解析维度）。"""
    from app.services.chart_payloads import attribution_radar_chart

    attr = {
        "dimensions": {
            "tax_health": {"label": "税务健康", "score": 55},
            "authenticity": {"label": "经营真实性", "score": 40},
            "legal": {"label": "法律合规", "score": 98},
        },
    }
    chart = attribution_radar_chart(attr, dims=["tax_health", "authenticity"])
    assert chart is not None
    names = [i["name"] for i in chart["data"]["indicators"]]
    assert "税务健康" in names
    assert "经营真实性" in names
    assert "法律合规" not in names  # 无对应章节 → 不画


def test_attribution_radar_legal_low_coverage_caveat():
    from app.services.chart_payloads import attribution_radar_chart

    attr = {
        "dimensions": {
            "legal": {
                "label": "法律合规",
                "score": 98,
                "coverage": "tax_illegal_only",
                "net_contribution": 4.9,
            },
        },
    }
    chart = attribution_radar_chart(attr)
    assert chart is not None
    assert any("低覆盖" in i["name"] for i in chart["data"]["indicators"])
    assert chart["data"].get("caveats")


def test_signal_funnel_chart_monotonic():
    from app.services.chart_payloads import signal_funnel_chart

    chart = signal_funnel_chart(100, {"e1"}, {"e2", "e3"}, {"e4"})
    assert chart["type"] == "funnel"
    vals = chart["data"]["values"]
    assert vals[0] >= vals[1] >= vals[2] >= vals[3]


def test_signal_industry_heatmap_requires_two_industries():
    from app.services.chart_payloads import signal_industry_heatmap, signal_pie_chart

    m1 = MagicMock(
        enterprise_id="e1",
        revenue_deviation=0.3,
        credit_level="C",
        tax_violation_cnt=0,
        industry_l1="制造",
    )
    m2 = MagicMock(
        enterprise_id="e2",
        revenue_deviation=0.1,
        credit_level="A",
        tax_violation_cnt=1,
        industry_l1="服务",
    )
    heatmap = signal_industry_heatmap([m1, m2])
    assert heatmap is not None
    assert heatmap["type"] == "heatmap"
    assert len(heatmap["data"]["y_labels"]) == 2

    pie = signal_pie_chart({"e2"}, {"e1"}, set())
    assert pie["type"] == "pie"
    assert sum(pie["data"]["series"][0]["values"]) == 2


def test_infer_chart_from_shape_without_hardcoded_type():
    """§9#8：带 shape 的数据块自动出图，不依赖手写 type。"""
    from app.services.chart_payloads import infer_chart, normalize_chart_payload

    block = {
        "shape": "categorical_distribution",
        "data": {"labels": ["制造", "服务"], "series": [{"name": "n", "values": [3, 2]}]},
    }
    chart = infer_chart(block)
    assert chart is not None
    assert chart["type"] == "bar"
    assert "制造" in chart["data"]["labels"]

    normalized = normalize_chart_payload(dict(block))
    assert normalized["type"] == "bar"
    assert normalized["shape"] == "categorical_distribution"


def test_normalize_overwrites_wrong_type_from_shape():
    from app.services.chart_payloads import normalize_chart_payload

    wrong = {
        "type": "pie",
        "shape": "ordered_series",
        "data": {"labels": ["2023", "2024"], "series": [{"name": "yoy", "values": [1, 2]}]},
    }
    fixed = normalize_chart_payload(wrong)
    assert fixed["type"] == "line"
