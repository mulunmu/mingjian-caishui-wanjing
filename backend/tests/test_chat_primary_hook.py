from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1 import chat as chat_api


@pytest.fixture(autouse=True)
def _disable_outer_orchestrator(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "false")


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


@pytest.mark.asyncio
async def test_chat_passes_report_approval_to_outer_orchestrator(monkeypatch):
    from app.services import outer_orchestrator

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    run = AsyncMock(
        return_value={
            "reply": "resumed",
            "session_id": "s1",
            "data": {"primary": {"status": "answered", "fallback": False}},
        }
    )
    monkeypatch.setattr(outer_orchestrator, "run_outer_turn", run)
    out = await chat_api.chat(
        body=chat_api.ChatRequest(
            query="确认生成报告",
            session_id="s1",
            approval=True,
        ),
        db=AsyncMock(),
        _user=None,
    )
    assert out["reply"] == "resumed"
    assert run.await_args.kwargs["approval"] is True


@pytest.mark.asyncio
async def test_chat_returns_scope_and_chart_from_primary(monkeypatch):
    from app.services import semantic_primary
    from app.services import session_store

    monkeypatch.setenv("SEMANTIC_PRIMARY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_PRIMARY_PERCENT", "100")
    monkeypatch.setattr(
        semantic_primary,
        "run_primary_turn",
        AsyncMock(
            return_value={
                "reply": "行业分布",
                "session_id": "s1",
                "charts": {"type": "bar", "data": {"labels": ["制造"], "series": []}},
                "data": {"primary": {"status": "answered", "fallback": False}},
            }
        ),
    )
    monkeypatch.setattr(
        session_store,
        "get_session",
        lambda _: {
            "dialogue_state": {
                "scope": "individual",
                "subject": {"enterprise_id": "ENT1", "display_name": "企业1"},
                "scenario": "warn",
            }
        },
    )

    out = await chat_api.chat(
        body=chat_api.ChatRequest(query="行业分布", session_id="s1"),
        db=AsyncMock(),
        _user=None,
    )
    assert out["dialogue_state"]["scope"] == "individual"
    assert out["ui"]["scope_bar"]["enterprise_id"] == "ENT1"
    assert out["charts"]["type"] == "bar"
