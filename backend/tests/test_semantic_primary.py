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
    from app.services.dialog_act import DialogAct

    captured = {}

    async def classify(query, context):
        del query, context
        return DialogAct(act="analyze", scenario="warn", confidence=0.9)

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
    monkeypatch.setattr(semantic_primary, "classify_dialog_act", classify)
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


@pytest.mark.asyncio
async def test_multi_intent_turn_merges_claims_and_persists_once(monkeypatch):
    from app.schemas.claim import Claim, ClaimTrace, ClaimValue
    from app.services import semantic_primary
    from app.services.dialog_act import DialogAct

    persisted = []
    composed_queries = []

    async def classify(query, context):
        del query, context
        return DialogAct(
            act="analyze",
            scenario="warn",
            scope_target="individual",
            confidence=0.95,
        )

    async def composer(**kwargs):
        query = kwargs["query"]
        composed_queries.append(query)
        if "资产负债率" in query:
            metric, number, query_id = "debt_ratio", 0.8, "Q-debt"
        else:
            metric, number, query_id = "cash_flow_net", -10.0, "Q-cash"
        route = ConversationRoute(
            route="analysis",
            domain="warn",
            entities=["ENT1"],
        )
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            claims=[
                Claim(
                    claim=f"{metric} claim",
                    value=ClaimValue(metric=metric, number=number, unit=""),
                    trace=ClaimTrace(
                        table="core_metrics",
                        field=metric,
                        query_id=query_id,
                    ),
                    confidence="computed",
                )
            ],
            reply=f"{metric} reply",
        )

    async def persist(**kwargs):
        persisted.append(kwargs)

    monkeypatch.setattr(semantic_primary.session_store, "get_session", lambda _: {})
    monkeypatch.setattr(semantic_primary, "classify_dialog_act", classify)
    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)
    out = await semantic_primary.run_primary_turn(
        db=object(),
        session_id="multi-intent",
        owner=None,
        query="分析ENT1的资产负债率；分析ENT1的现金流",
        enterprise_id="ENT1",
    )
    primary = out["data"]["primary"]
    assert len(composed_queries) == 2
    assert len(persisted) == 1
    assert len(persisted[0]["turn"].claims) == 2
    assert primary["multi_intent"] is True
    assert primary["multi_intent_segments"] == [
        "分析ENT1的资产负债率",
        "分析ENT1的现金流",
    ]
    assert primary["dialogue_composition_plan_id"].startswith("dialogue-2-")
    assert len(out["data"]["claims"]) == 2


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


def test_semantic_plan_route_overrides_stale_raw_route():
    from app.schemas.semantic_plan import SemanticPlan
    from app.services import semantic_primary

    route = ConversationRoute(route="inventory")
    raw_route = {
        "route": "inventory",
        "action": "metadata_query",
        "entities": [],
        "filters": {},
    }
    plan = SemanticPlan(
        action="conversation",
        route_hint="capability",
        confidence=0.92,
    )

    raw_route, route = semantic_primary.apply_semantic_plan_route(
        route=route,
        raw_route=raw_route,
        plan=plan,
    )

    assert raw_route["route"] == "capability"
    assert "action" not in raw_route
    assert raw_route["needs_tools"] is False
    assert route.route == "capability"
    assert route.needs_tools is False


def test_plan_analysis_focus_is_persistable_for_followups():
    from app.schemas.semantic_plan import SemanticPlan, SemanticPlanStep
    from app.services import semantic_primary

    plan = SemanticPlan(
        action="analysis",
        scope="cohort",
        filters={"industry_l1": ["其他"]},
        steps=[
            SemanticPlanStep(
                step_id="s1",
                tool_id="metric_authenticity_score",
                filters={"industry_l1": ["其他"]},
            )
        ],
        confidence=0.9,
    )

    focus = semantic_primary.plan_analysis_focus(plan)

    assert focus["industry_l1"] == "其他"
    assert focus["industry_l1_values"] == ["其他"]
