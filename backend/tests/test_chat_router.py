"""Chat 路由服务单元测试"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_chart_helpers():
    from app.services.chat_router import _radar_chart, _bar_chart

    ent = {
        "enterprise_name": "Test",
        "dimensions": {
            "tax_health": 80,
            "authenticity": 70,
            "invoice": 68,
            "industry": 75,
            "legal": 85,
            "finance": 65,
        },
    }
    radar = _radar_chart(ent)
    assert radar["type"] == "radar"
    assert len(radar["data"]["values"]) == 6  # 六维（含发票健康）

    items = [
        {"industry_l1": "制造", "avg_revenue_yoy": 5.2},
        {"industry_l1": "服务", "avg_revenue_yoy": 1.1},
    ]
    bar = _bar_chart(items, metric="avg_revenue_yoy", title="同比%")
    assert bar["type"] == "bar"
    assert len(bar["data"]["labels"]) == 2


def test_missing_enterprise_message():
    from app.services.chat_router import _missing_enterprise_message

    msg = _missing_enterprise_message("score")
    assert "行业" in msg or "趋势" in msg


def test_unknown_enterprise_message():
    from app.services.chat_router import _unknown_enterprise_message

    msg = _unknown_enterprise_message()
    assert "匿名" in msg or "行业" in msg
