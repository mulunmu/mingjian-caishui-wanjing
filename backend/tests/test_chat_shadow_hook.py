from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import chat as chat_api


@pytest.mark.asyncio
async def test_shadow_hook_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SHADOW_SEMANTIC_ENABLED", raising=False)
    monkeypatch.setattr(
        chat_api,
        "route_chat",
        AsyncMock(return_value={"reply": "ok", "session_id": "s1", "data": {}}),
    )
    body = chat_api.ChatRequest(query="你好", session_id="s1")
    out = await chat_api.chat(body=body, db=AsyncMock(), _user=None)
    assert out["reply"] == "ok"
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