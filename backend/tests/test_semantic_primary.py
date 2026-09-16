from __future__ import annotations

import pytest

from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.schemas.semantic_turn import SemanticTurnResult
from app.schemas.semantic_frame import SemanticFrame


@pytest.mark.asyncio
async def test_primary_routes_non_analysis_without_composer(monkeypatch):
    from app.services import semantic_primary

    called = False

    async def composer(**kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    out = await semantic_primary.compose_primary_turn(
        db=object(),
        session_id="s1",
        query="你好",
        raw_route={"route": "greeting"},
    )
    assert out.status == "answered"
    assert out.route.route == "greeting"
    assert called is False


@pytest.mark.asyncio
async def test_not_applicable_is_contract_error(monkeypatch):
    from app.services import semantic_primary

    route = ConversationRoute(route="analysis")

    async def composer(**kwargs):
        return SemanticTurnResult(
            status="not_applicable",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
        )

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    with pytest.raises(semantic_primary.PrimaryContractError):
        await semantic_primary.compose_primary_turn(
            db=object(),
            session_id="s1",
            query="分析风险",
            raw_route={"route": "analysis"},
        )


@pytest.mark.asyncio
async def test_non_analysis_not_applicable_falls_back_to_policy_handler(monkeypatch):
    from app.services import semantic_primary

    route = ConversationRoute(route="capability", entities=["ENT1"])

    async def composer(**kwargs):
        return SemanticTurnResult(
            status="not_applicable",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
        )

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    out = await semantic_primary.compose_primary_turn(
        db=object(),
        session_id="s1",
        query="你好",
        raw_route={
            "route": "capability",
            "entities": ["ENT1"],
            "needs_tools": False,
        },
    )
    assert out.status == "answered"
    assert out.route.route == "capability"


@pytest.mark.asyncio
async def test_primary_turn_injects_referenced_topic_context(monkeypatch):
    from app.services import semantic_primary

    captured = {}

    monkeypatch.setattr(
        semantic_primary,
        "resolve_topic_reference_blocking",
        lambda *args, **kwargs: {
            "topic_id": "s1-topic-4",
            "summary": "现金流净额偏弱",
            "entities": ["ENT1"],
            "filters": {},
            "scenario": "loan",
            "intent": "analysis",
        },
    )

    async def composer(**kwargs):
        captured.update(kwargs)
        route = ConversationRoute(route="analysis", domain="loan", entities=["ENT1"])
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply="现金流净额偏弱",
            reply_source="llm",
        )

    async def persist(**kwargs):
        return None

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)
    out = await semantic_primary.run_primary_turn(
        db=object(),
        session_id="s1",
        owner=None,
        query="回到上上个问题，继续分析",
    )
    assert captured["raw_route"]["route"] == "analysis"
    assert captured["raw_route"]["entities"] == ["ENT1"]
    assert "现金流净额偏弱" in captured["query"]
    assert out["data"]["primary"]["referenced_topic_id"] == "s1-topic-4"


@pytest.mark.asyncio
async def test_primary_turn_injects_explicit_enterprise_id(monkeypatch):
    from app.services import semantic_primary

    captured = {}

    async def composer(**kwargs):
        captured.update(kwargs)
        route = ConversationRoute(route="analysis", domain="warn", entities=["ENT9"])
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply="资产负债率偏高",
        )

    async def persist(**kwargs):
        return None

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)
    await semantic_primary.run_primary_turn(
        db=object(),
        session_id="s1",
        owner=None,
        query="资产负债率高不高",
        enterprise_id="ENT9",
    )
    assert captured["raw_route"]["entities"] == ["ENT9"]


@pytest.mark.asyncio
async def test_primary_turn_skips_memory_context_without_topic_reference(monkeypatch):
    from app.services import semantic_primary

    memory_called = False

    def memory_context(*args, **kwargs):
        nonlocal memory_called
        memory_called = True
        return {}

    async def composer(**kwargs):
        route = ConversationRoute(route="analysis", domain="warn", entities=["ENT9"])
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply="资产负债率偏高",
        )

    async def persist(**kwargs):
        return None

    monkeypatch.setattr(semantic_primary, "compose_memory_context_blocking", memory_context)
    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)
    await semantic_primary.run_primary_turn(
        db=object(),
        session_id="s1",
        owner=None,
        query="资产负债率高不高",
        enterprise_id="ENT9",
    )
    assert memory_called is False


@pytest.mark.asyncio
async def test_primary_turn_degrades_when_memory_context_is_unavailable(monkeypatch):
    from app.services import semantic_primary

    captured = {}

    def memory_context(*args, **kwargs):
        raise RuntimeError("memory database unavailable")

    def resolve(*args, **kwargs):
        return None

    async def composer(**kwargs):
        captured.update(kwargs)
        route = ConversationRoute(route="analysis", domain="warn")
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply="继续分析",
        )

    async def persist(**kwargs):
        return None

    monkeypatch.setattr(semantic_primary, "compose_memory_context_blocking", memory_context)
    monkeypatch.setattr(semantic_primary, "resolve_topic_reference_blocking", resolve)
    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)
    out = await semantic_primary.run_primary_turn(
        db=object(),
        session_id="s1",
        owner=None,
        query="回到上一个问题继续分析",
        raw_route={"route": "analysis", "domain": "warn"},
    )
    assert out["data"]["primary"]["status"] == "answered"
    assert captured["query"] == "回到上一个问题继续分析"


@pytest.mark.asyncio
async def test_primary_turn_keeps_topic_resolution_fail_closed(monkeypatch):
    from app.services import semantic_primary

    def memory_context(*args, **kwargs):
        return {}

    def resolve(*args, **kwargs):
        raise RuntimeError("topic database unavailable")

    async def persist(**kwargs):
        return None

    monkeypatch.setattr(semantic_primary, "compose_memory_context_blocking", memory_context)
    monkeypatch.setattr(semantic_primary, "resolve_topic_reference_blocking", resolve)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)
    with pytest.raises(RuntimeError, match="topic database unavailable"):
        await semantic_primary.run_primary_turn(
            db=object(),
            session_id="s1",
            owner=None,
            query="回到上一个问题继续分析",
            raw_route={"route": "analysis", "domain": "warn"},
        )


def test_structured_multi_metric_frame_promotes_weak_route():
    from app.services import semantic_primary

    route = ConversationRoute(route="clarify", entities=["ENT1"])
    frame = SemanticFrame(
        policy_route="clarify",
        task_type="multi_metric",
        subject_scope="individual",
        entities=["ENT1"],
        metrics=["debt_ratio", "red_invoice_cnt"],
    )
    promoted = semantic_primary.promote_route_with_frame(route, frame)
    assert promoted.route == "analysis"
    assert promoted.needs_tools is True
    assert promoted.needs_clarification is False
