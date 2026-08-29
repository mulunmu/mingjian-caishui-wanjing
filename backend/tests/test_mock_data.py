"""Mock 数据服务单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.mock_data import (
    get_mock_enterprise, get_all_mock_enterprises,
    get_mock_warnings, get_mock_legal_events, MOCK_ENTERPRISES,
)


def test_mock_enterprise_count():
    assert len(MOCK_ENTERPRISES) == 10


def test_get_mock_enterprise():
    ent = get_mock_enterprise("ENT001")
    assert ent is not None
    assert "·" in ent["enterprise_name"]
    assert ent["enterprise_name"] == ent.get("display_label")
    assert "深圳明达" not in ent["enterprise_name"]
    assert ent["source"] == "mock"
    assert "dimensions" in ent
    assert len(ent["dimensions"]) == 6


def test_get_nonexistent_enterprise():
    assert get_mock_enterprise("ENT999") is None


def test_all_have_source_mock():
    for ent in get_all_mock_enterprises():
        assert ent["source"] == "mock"


def test_warnings_not_empty():
    warnings = get_mock_warnings()
    assert len(warnings) > 0
    for w in warnings:
        assert len(w["warning_signals"]) > 0


def test_legal_events():
    events = get_mock_legal_events("ENT006")
    assert len(events) == 3
    assert events[0]["severity"] == "H"


def test_social_trend_chinese():
    """验证 social_trend 使用中文枚举"""
    for ent in MOCK_ENTERPRISES:
        trend = ent.get("social_trend", "")
        assert trend in ("增长", "稳定", "缩减"), f"Unexpected social_trend: {trend}"
