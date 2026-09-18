from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_demo_scope_change_uses_real_anonymized_enterprise(monkeypatch):
    from app.services import llm_reply, scope_control, session_store

    stored: dict = {}

    async def fake_demo(_db):
        return ("hash-1", "企业1")

    async def fake_policy_reply(**kwargs):
        return ("已切换到企业1", "llm")

    def fake_store(*args, **kwargs):
        stored.update(kwargs)
        return True

    monkeypatch.setattr(scope_control, "_demo_enterprise", fake_demo)
    monkeypatch.setattr(llm_reply, "generate_policy_reply", fake_policy_reply)
    monkeypatch.setattr(session_store, "get_session", lambda _: {})
    monkeypatch.setattr(session_store, "store_session", fake_store)

    out = await scope_control.handle_scope_change(
        db=object(),
        session_id="s1",
        owner=None,
        followup={
            "type": "switch_scope",
            "label": "试用演示企业",
            "target": "individual",
            "params": {"use_demo": True},
        },
    )

    assert out["dialogue_state"]["scope"] == "individual"
    assert out["dialogue_state"]["subject"]["display_name"] == "企业1"
    assert out["dialogue_state"]["subject"]["enterprise_id"] == "hash-1"
    assert stored["dialogue_state"]["subject"]["enterprise_id"] == "hash-1"
    assert out["reply_source"] == "llm"


@pytest.mark.asyncio
async def test_cohort_scope_change_clears_enterprise(monkeypatch):
    from app.services import llm_reply, scope_control, session_store, scope_state

    current = scope_state.switch_scope(
        scope_state.empty_dialogue_state(),
        target="individual",
        subject={"enterprise_id": "hash-1", "display_name": "企业1"},
    )

    async def fake_policy_reply(**kwargs):
        return ("已切换到全库", "llm")

    monkeypatch.setattr(
        session_store,
        "get_session",
        lambda _: {"dialogue_state": current},
    )
    monkeypatch.setattr(session_store, "store_session", lambda *a, **k: True)
    monkeypatch.setattr(llm_reply, "generate_policy_reply", fake_policy_reply)

    out = await scope_control.handle_scope_change(
        db=object(),
        session_id="s1",
        owner=None,
        followup={
            "type": "switch_scope",
            "label": "看全库群体",
            "target": "cohort",
        },
    )

    assert out["dialogue_state"]["scope"] == "cohort"
    assert out["dialogue_state"]["subject"] is None
