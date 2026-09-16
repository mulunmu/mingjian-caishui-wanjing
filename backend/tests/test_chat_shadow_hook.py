from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import chat as chat_api


@pytest.mark.asyncio
async def test_chat_uses_primary_even_when_shadow_is_disabled(monkeypatch):
    from app.services import semantic_primary

    monkeypatch.delenv("SHADOW_SEMANTIC_ENABLED", raising=False)
    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setattr(
        semantic_primary,
        "run_primary_turn",
        AsyncMock(return_value={"reply": "primary ok", "session_id": "s1", "data": {}}),
    )
    body = chat_api.ChatRequest(query="你好", session_id="s1")
    out = await chat_api.chat(body=body, db=AsyncMock(), _user=None)
    assert out["reply"] == "primary ok"
    assert out["session_note"] == chat_api.SESSION_NOTE


@pytest.mark.asyncio
async def test_shadow_hook_swallows_its_own_failures(monkeypatch):
    monkeypatch.setenv("SHADOW_SEMANTIC_ENABLED", "true")

    def fail(*args, **kwargs):
        raise RuntimeError("shadow unavailable")

    from app.services import shadow_integration

    monkeypatch.setattr(
        shadow_integration,
        "run_shadow_evaluation_sync",
        fail,
    )
    result = {"reply": "legacy ok", "session_id": "s1", "data": {}}
    await chat_api._maybe_run_shadow(
        "你好",
        result,
        session_id="s1",
        legacy_latency_ms=12.0,
    )
    assert result["reply"] == "legacy ok"

@pytest.mark.asyncio
async def test_canary_hook_selected_replaces_legacy_reply(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.services import canary_router, semantic_answer_composer, session_store

    monkeypatch.setattr(canary_router, "canary_percent", lambda: 100)
    monkeypatch.setattr(
        chat_api,
        "_resolve_shadow_raw_route",
        AsyncMock(return_value={"route": "analysis", "domain": "warn"}),
    )
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
        semantic_answer_composer,
        "compose_semantic_turn",
        AsyncMock(return_value=semantic),
    )
    monkeypatch.setattr(session_store, "replace_last_reply", lambda *a, **k: True)
    result = {"reply": "legacy reply", "session_id": "s1", "data": {}}
    await chat_api._maybe_apply_canary(
        "企业1资产负债率高不高",
        result,
        session_id="s1",
        owner=None,
        db=object(),
    )
    assert result["reply"] == "semantic reply"
    assert result["data"]["canary"]["status"] == "answered"


@pytest.mark.asyncio
async def test_canary_hook_failure_does_not_leak_error_or_replace_reply(monkeypatch):
    from app.services import canary_router, semantic_answer_composer

    monkeypatch.setattr(canary_router, "canary_percent", lambda: 100)
    monkeypatch.setattr(
        chat_api,
        "_resolve_shadow_raw_route",
        AsyncMock(return_value={"route": "analysis", "domain": "warn"}),
    )
    monkeypatch.setattr(
        semantic_answer_composer,
        "compose_semantic_turn",
        AsyncMock(side_effect=RuntimeError("internal-secret")),
    )
    result = {"reply": "legacy reply", "session_id": "s1", "data": {}}
    await chat_api._maybe_apply_canary(
        "企业1资产负债率高不高",
        result,
        session_id="s1",
        owner=None,
        db=object(),
    )
    assert result["reply"] == "legacy reply"
    assert result["data"]["canary"] == {"status": "error", "fallback": "legacy"}
    assert "internal-secret" not in str(result)
