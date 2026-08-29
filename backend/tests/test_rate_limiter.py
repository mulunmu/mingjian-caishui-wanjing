"""速率限制器单元测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.rate_limiter import check_api_limit, record_api_call


def test_api_limit_allows_requests():
    """初始状态应允许请求"""
    for _ in range(5):
        assert check_api_limit()
        record_api_call()


def test_llm_daily_limit():
    from app.services.rate_limiter import (
        LLM_DAILY_LIMIT_PER_KEY,
        check_llm_limit,
        increment_llm,
        get_llm_usage,
        set_request_client_key,
    )

    set_request_client_key("test-client-a")
    assert check_llm_limit()
    usage = get_llm_usage()
    assert "used" in usage
    assert usage["limit"] == LLM_DAILY_LIMIT_PER_KEY
    assert usage.get("key") == "test-client-a"


def test_llm_quota_isolated_per_client():
    from app.services.rate_limiter import check_llm_limit, increment_llm, set_request_client_key

    set_request_client_key("client-x")
    for _ in range(3):
        increment_llm()
    set_request_client_key("client-y")
    # 另一客户端不应被 client-x 的计数拖垮（在未达上限时仍可用）
    assert check_llm_limit()


def test_get_llm_usage_structure():
    from app.services.rate_limiter import get_llm_usage
    usage = get_llm_usage()
    assert isinstance(usage, dict)
    assert "date" in usage
    assert "remaining" in usage


def test_llm_available_respects_daily_quota(monkeypatch):
    """配额耗尽时 llm_available() 返回 False（降级规则模式），而非硬抛 429。"""
    from app.services import llm_reply, rate_limiter

    monkeypatch.setattr(llm_reply, "_is_llm_configured", lambda: True)
    monkeypatch.setattr(rate_limiter, "check_llm_limit", lambda: False)
    assert llm_reply.llm_available() is False

    monkeypatch.setattr(rate_limiter, "check_llm_limit", lambda: True)
    assert llm_reply.llm_available() is True

    monkeypatch.setattr(llm_reply, "_is_llm_configured", lambda: False)
    assert llm_reply.llm_available() is False
