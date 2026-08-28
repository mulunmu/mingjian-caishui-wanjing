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
    from app.services.rate_limiter import LLM_DAILY_LIMIT, check_llm_limit, increment_llm, get_llm_usage
    assert check_llm_limit()
    usage = get_llm_usage()
    assert "used" in usage
    # 上限来自环境变量（默认 100，dev compose 为 1000），测试不应硬编码
    assert usage["limit"] == LLM_DAILY_LIMIT


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
