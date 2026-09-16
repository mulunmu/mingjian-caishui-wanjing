from __future__ import annotations

import pytest

from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.schemas.semantic_turn import SemanticTurnResult


@pytest.mark.asyncio
async def test_primary_turn_persists_history_and_topic(monkeypatch):
    from app.services import semantic_turn_persistence as stp

    calls = []

    def fake_store(*args, **kwargs):
        calls.append(("history", kwargs))
        return True

    def fake_topic(*args, **kwargs):
        calls.append(("topic", kwargs))

    monkeypatch.setattr(stp.session_store, "store_session", fake_store)
    monkeypatch.setattr(stp, "append_topic_blocking", fake_topic)
    monkeypatch.setattr(stp, "get_sync_engine", lambda: object())

    route = ConversationRoute(route="greeting", domain="general")
    turn = SemanticTurnResult(
        status="answered",
        route=route,
        policy=ConversationPolicyRegistry.resolve(route),
        reply="你好",
    )
    await stp.persist_primary_turn(
        db=object(),
        session_id="s1",
        owner="u@example.com",
        query="你好",
        turn=turn,
    )
    assert [item[0] for item in calls] == ["history", "topic"]
    assert calls[0][1]["reply"] == "你好"
    assert calls[1][1]["intent"] == "greeting"


@pytest.mark.asyncio
async def test_history_failure_prevents_topic_write(monkeypatch):
    from app.services import semantic_turn_persistence as stp

    topic_called = False

    def fake_topic(*args, **kwargs):
        nonlocal topic_called
        topic_called = True

    monkeypatch.setattr(stp.session_store, "store_session", lambda *a, **k: False)
    monkeypatch.setattr(stp, "append_topic_blocking", fake_topic)

    route = ConversationRoute(route="greeting", domain="general")
    turn = SemanticTurnResult(
        status="answered",
        route=route,
        policy=ConversationPolicyRegistry.resolve(route),
        reply="你好",
    )
    with pytest.raises(stp.PrimaryPersistenceError):
        await stp.persist_primary_turn(
            db=object(),
            session_id="s1",
            owner=None,
            query="你好",
            turn=turn,
        )
    assert topic_called is False
