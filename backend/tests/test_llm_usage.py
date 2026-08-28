"""LLM 配额计数：避免内部补全重复计入每日上限"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_plain_completion_does_not_increment_quota(monkeypatch):
    from app.services import rate_limiter
    from app.services import llm_reply

    calls: list[int] = []
    monkeypatch.setattr(rate_limiter, "increment", lambda: calls.append(1))
    monkeypatch.setattr(llm_reply, "_is_llm_configured", lambda: True)
    monkeypatch.setattr(llm_reply, "_llm_completion_params", lambda: ("test-model", {"api_key": "k"}))
    monkeypatch.setattr(llm_reply, "_llm_extra_body", lambda _m: None)

    def fake_completion(**_kwargs):
        msg = MagicMock()
        msg.content = "ok"
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    monkeypatch.setattr("litellm.completion", fake_completion)

    text = await llm_reply._plain_completion("system", "user")
    assert text == "ok"
    assert calls == []


def test_record_llm_usage_increments_once():
    from app.services.llm_reply import _record_llm_usage
    from app.services.rate_limiter import get_llm_usage

    before = get_llm_usage()["used"]
    _record_llm_usage()
    after = get_llm_usage()["used"]
    assert after == before + 1


@pytest.mark.asyncio
async def test_classify_intent_llm_does_not_increment_quota(monkeypatch):
    """意图复审（发散问题兜底）是单轮内部调用，不应重复计入每日对话配额。"""
    from app.services import rate_limiter
    from app.services import llm_reply

    calls: list[int] = []
    monkeypatch.setattr(rate_limiter, "increment", lambda: calls.append(1))
    monkeypatch.setattr(llm_reply, "_is_llm_configured", lambda: True)

    async def fake_plain(_system, _user, **_kwargs):
        return '{"function": "trend", "dimension": "industry", "industry_l1": "制造业"}'

    monkeypatch.setattr(llm_reply, "_plain_completion", fake_plain)

    result = await llm_reply.classify_intent_llm("分析制造业的趋势")
    assert result is not None and result["function"] == "trend"
    assert calls == []
