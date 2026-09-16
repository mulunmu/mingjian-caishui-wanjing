from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1 import chat as chat_api


@pytest.mark.asyncio
async def test_primary_selected_does_not_call_legacy(monkeypatch):
    from app.services import semantic_primary

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setenv("SHADOW_SEMANTIC_INDEPENDENT_ROUTE", "true")
    assert not hasattr(chat_api, "run_legacy_compat")
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
async def test_primary_internal_failure_returns_503_without_legacy_fallback(monkeypatch):
    from app.services import semantic_primary

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setenv("SHADOW_SEMANTIC_INDEPENDENT_ROUTE", "true")
    monkeypatch.setattr(
        semantic_primary,
        "run_primary_turn",
        AsyncMock(side_effect=RuntimeError("internal-secret")),
    )
    with pytest.raises(HTTPException) as exc_info:
        await chat_api.chat(
            body=chat_api.ChatRequest(query="你好", session_id="s1"),
            db=AsyncMock(),
            _user=None,
        )
    assert exc_info.value.status_code == 503
    assert "internal-secret" not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_disabled_primary_is_fail_closed(monkeypatch):
    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "false")
    with pytest.raises(HTTPException) as exc_info:
        await chat_api.chat(
            body=chat_api.ChatRequest(query="你好", session_id="s1"),
            db=AsyncMock(),
            _user=None,
        )
    assert exc_info.value.status_code == 503
