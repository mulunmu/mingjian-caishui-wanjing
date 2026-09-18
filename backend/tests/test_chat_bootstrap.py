from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_bootstrap_returns_ui_without_recording_history(monkeypatch):
    from app.api.v1 import chat
    from app.services import session_store

    state = {
        "scope": "individual",
        "subject": {"enterprise_id": "企业1", "display_name": "企业1"},
        "scenario": "warn",
    }
    monkeypatch.setattr(session_store, "ensure_session_id", lambda *_: "bootstrap-session")
    monkeypatch.setattr(session_store, "get_session", lambda _: {"dialogue_state": state})

    def fail_store(*args, **kwargs):
        raise AssertionError("bootstrap must not persist a conversation turn")

    monkeypatch.setattr(session_store, "store_session", fail_store)
    from app.services import llm_reply

    async def fake_policy_reply(**kwargs):
        return ("动态欢迎语", "llm")

    monkeypatch.setattr(llm_reply, "generate_policy_reply", fake_policy_reply)

    response = await chat.bootstrap_chat_session(
        session_id="bootstrap-session",
        user=None,
    )

    assert response["session_id"] == "bootstrap-session"
    assert response["dialogue_state"]["scope"] == "individual"
    assert response["ui"]["scope_bar"]["enterprise_id"] == "企业1"
    assert response["ui"]["welcome"] == "动态欢迎语"
    assert response["welcome_source"] == "llm"


@pytest.mark.asyncio
async def test_bootstrap_fails_closed_without_llm_welcome(monkeypatch):
    from app.api.v1 import chat
    from app.services import llm_reply, session_store

    monkeypatch.setattr(session_store, "ensure_session_id", lambda *_: "s1")
    monkeypatch.setattr(session_store, "get_session", lambda _: {})

    async def empty_policy_reply(**kwargs):
        return ("", "template")

    monkeypatch.setattr(llm_reply, "generate_policy_reply", empty_policy_reply)

    response = await chat.bootstrap_chat_session(session_id="s1", user=None)

    assert response["ui"]["welcome"] == ""
