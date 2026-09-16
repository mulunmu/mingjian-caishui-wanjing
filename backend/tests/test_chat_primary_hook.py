from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import chat as chat_api


@pytest.mark.asyncio
async def test_primary_selected_does_not_call_legacy(monkeypatch):
    from app.services import semantic_primary

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setenv("SHADOW_SEMANTIC_INDEPENDENT_ROUTE", "true")
    monkeypatch.setattr(
        chat_api,
        "route_chat",
        AsyncMock(side_effect=AssertionError("legacy called")),
    )
    monkeypatch.setattr(
        semantic_primary,
        "run_primary_turn",
        AsyncMock(
            return_value={
                "reply": "semantic",
                "session_id": "s1",
                "data": {"primary": {"status": "answered", "fallback": False}},
            }
        ),
    )
    out = await chat_api.chat(
        body=chat_api.ChatRequest(query="你好", session_id="s1"),
        db=AsyncMock(),
        _user=None,
    )
    assert out["reply"] == "semantic"
    assert out["data"]["primary"]["fallback"] is False


@pytest.mark.asyncio
async def test_primary_internal_failure_falls_back(monkeypatch):
    from app.services import semantic_primary

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setenv("SHADOW_SEMANTIC_INDEPENDENT_ROUTE", "true")
    monkeypatch.setattr(
        semantic_primary,
        "run_primary_turn",
        AsyncMock(side_effect=RuntimeError("internal-secret")),
    )
    monkeypatch.setattr(
        chat_api,
        "route_chat",
        AsyncMock(return_value={"reply": "legacy", "session_id": "s1", "data": {}}),
    )
    out = await chat_api.chat(
        body=chat_api.ChatRequest(query="你好", session_id="s1"),
        db=AsyncMock(),
        _user=None,
    )
    assert out["reply"] == "legacy"
    assert out["data"]["primary"]["fallback"] is True
    assert out["data"]["primary"]["fallback_reason"] == "internal_error"
    assert "internal-secret" not in str(out)
