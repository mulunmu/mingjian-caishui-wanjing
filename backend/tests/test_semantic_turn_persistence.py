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
        meta={"report_id": "report-1", "report": {"report_id": "report-1"}},
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
    assert calls[1][1]["report_ids"] == ["report-1"]


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


@pytest.mark.asyncio
async def test_dialogue_state_keeps_human_entity_label(monkeypatch):
    from app.schemas.tool_plan import ToolPlan, ToolStep
    from app.services import semantic_turn_persistence as stp

    captured = {}

    def fake_store(*args, **kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(stp.session_store, "store_session", fake_store)
    monkeypatch.setattr(stp, "append_topic_blocking", lambda *a, **k: None)
    monkeypatch.setattr(stp, "get_sync_engine", lambda: object())

    route = ConversationRoute(route="analysis", domain="warn", entities=["企业1"])
    turn = SemanticTurnResult(
        status="answered",
        route=route,
        policy=ConversationPolicyRegistry.resolve(route),
        plan=ToolPlan(
            mode="answer",
            steps=[
                ToolStep(
                    step_id="s1",
                    tool_id="metric_overall_score",
                    params={"entity": "hash-1", "query": "企业1风险"},
                )
            ],
        ),
        meta={"entity_display_names": {"hash-1": "企业1"}},
    )

    await stp.persist_primary_turn(
        db=object(),
        session_id="s1",
        owner=None,
        query="企业1风险",
        turn=turn,
    )

    assert captured["dialogue_state"]["subject"]["enterprise_id"] == "hash-1"
    assert captured["dialogue_state"]["subject"]["display_name"] == "企业1"
