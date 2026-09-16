from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.canary_router import (
    apply_canary_result,
    canary_bucket,
    canary_percent,
    is_canary_selected,
)


def test_canary_bucket_is_deterministic():
    assert canary_bucket("session-1") == canary_bucket("session-1")
    assert 0 <= canary_bucket("session-1") < 100


def test_canary_zero_and_full_percentages():
    assert is_canary_selected("session-1", 0) is False
    assert is_canary_selected("session-1", 100) is True
    assert is_canary_selected("session-1", "not-a-number") is False


def test_canary_percent_invalid_environment_falls_back_to_zero(monkeypatch):
    monkeypatch.setenv("SEMANTIC_CANARY_PERCENT", "invalid")
    assert canary_percent() == 0.0
    monkeypatch.setenv("SEMANTIC_CANARY_PERCENT", "nan")
    assert canary_percent() == 0.0


@pytest.mark.asyncio
async def test_apply_canary_result_replaces_successful_legacy_reply(monkeypatch):
    claim = Claim(
        claim="资产负债率 72.00。",
        value=ClaimValue(metric="debt_ratio", number=72.0, unit="%"),
        trace=ClaimTrace(table="core_metrics", field="debt_ratio", query_id="Q"),
        confidence="computed",
    )
    semantic = MagicMock(
        status="answered",
        reply="资产负债率 72.00，偿债压力需要结合现金流判断。",
        reply_source="llm",
        claims=[claim],
        followups=["继续看现金流"],
        route=MagicMock(route="analysis", domain="warn"),
        plan=MagicMock(steps=[MagicMock(tool_id="metric_debt_ratio")]),
        candidates=[MagicMock(tool_id="metric_debt_ratio")],
    )
    monkeypatch.setattr(
        "app.services.session_store.replace_last_reply",
        lambda *a, **k: True,
    )
    legacy = {
        "reply": "old reply",
        "reply_source": "template",
        "session_id": "s1",
        "data": {"claims": [], "followups": []},
    }
    out = await apply_canary_result(legacy, semantic, owner=None)
    assert out["reply"] == semantic.reply
    assert out["reply_source"] == "llm"
    assert out["data"]["canary"]["status"] == "answered"
    assert out["data"]["claims"][0]["value"]["metric"] == "debt_ratio"
    assert out["data"]["followups"] == ["继续看现金流"]


@pytest.mark.asyncio
async def test_apply_canary_result_falls_back_when_semantic_not_answered(monkeypatch):
    semantic = MagicMock(status="clarify", reply=None, claims=[], followups=[])
    legacy = {"reply": "old reply", "session_id": "s1", "data": {}}
    out = await apply_canary_result(legacy, semantic, owner=None)
    assert out["reply"] == "old reply"
    assert out["data"]["canary"]["status"] == "clarify"


@pytest.mark.asyncio
async def test_apply_canary_result_falls_back_when_history_replace_fails(monkeypatch):
    semantic = MagicMock(
        status="answered",
        reply="semantic reply",
        reply_source="llm",
        claims=[],
        followups=[],
        route=MagicMock(route="analysis", domain="warn"),
        plan=None,
        candidates=[],
    )
    monkeypatch.setattr(
        "app.services.session_store.replace_last_reply",
        lambda *a, **k: False,
    )
    legacy = {
        "reply": "old reply",
        "reply_source": "template",
        "session_id": "s1",
        "data": {},
    }
    out = await apply_canary_result(legacy, semantic, owner=None)
    assert out["reply"] == "old reply"
    assert out["reply_source"] == "template"
    assert out["data"]["canary"]["status"] == "persistence_failed"
