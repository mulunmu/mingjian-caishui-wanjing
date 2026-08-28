"""边界情况测试 — 覆盖异常输入和极端场景"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_intent_empty_query():
    from app.services.intent_engine import recognize
    result = recognize("")
    assert result.intent == "general"


def test_intent_very_short():
    from app.services.intent_engine import recognize
    result = recognize("?")
    assert result.function == "general"


def test_enterprise_not_found():
    from app.services.mock_data import get_mock_enterprise
    assert get_mock_enterprise("ENT999") is None
    assert get_mock_enterprise("") is None


def test_warning_signals_non_empty():
    from app.services.mock_data import get_mock_warnings
    warnings = get_mock_warnings()
    for w in warnings:
        assert len(w["warning_signals"]) > 0
        assert w["risk_level"] != "低风险"


def test_auth_weak_password():
    from app.services.auth_service import register_user
    raised = False
    try:
        register_user("weak@test.com", "123")
    except ValueError:
        raised = True
    assert raised


def test_auth_nonexistent_user():
    from app.services.auth_service import authenticate_user
    assert authenticate_user("noone@nowhere.com", "anything") is None


def test_rate_limit_boundary():
    from app.services.rate_limiter import check_api_limit, record_api_call
    # 确保不超限时可以继续
    assert check_api_limit()
    record_api_call()


def test_mock_data_no_empty_names():
    from app.services.mock_data import MOCK_ENTERPRISES
    for ent in MOCK_ENTERPRISES:
        assert len(ent["enterprise_name"]) > 0
        assert len(ent["enterprise_id"]) > 0
