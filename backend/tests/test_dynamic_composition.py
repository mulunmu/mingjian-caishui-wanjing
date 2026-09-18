from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.schemas.composition import ModuleSpec, PortSpec
from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.services.composition_planner import build_open_overview_plan
from app.services.composition_validator import validate_composition_plan
from app.services.semantic_frame import frame_from_route


def _metric_module(module_id: str, scenarios: tuple[str, ...] = ()) -> ModuleSpec:
    return ModuleSpec(
        module_id=module_id,
        kind="metric",
        version="1",
        status="validated",
        inputs=[
            PortSpec(name="entity", data_type="entity", required=False),
            PortSpec(name="filters", data_type="filters", required=False),
        ],
        outputs=[PortSpec(name="claims", data_type="claims")],
        metadata={"scenarios": list(scenarios)},
    )


def test_open_overview_query_becomes_structured_task():
    route = ConversationRoute(route="analysis", domain="warn", entities=["企业1"])
    frame = frame_from_route(route, query="企业1有哪些值得分析的点")

    assert frame.task_type == "open_overview"
    assert frame.subject_scope == "individual"
    assert frame.entities == ["企业1"]


def test_dynamic_overview_plan_uses_multiple_candidate_modules():
    modules = {
        "metric_finance_score": _metric_module("metric_finance_score", ("loan",)),
        "metric_tax_health_score": _metric_module("metric_tax_health_score", ("audit",)),
        "metric_invoice_score": _metric_module("metric_invoice_score", ("warn",)),
        "metric_authenticity_score": _metric_module("metric_authenticity_score", ("rating",)),
    }
    frame = SemanticFrame(
        policy_route="analysis",
        task_type="open_overview",
        subject_scope="individual",
        entities=["企业1"],
    )

    plan = build_open_overview_plan(
        frame=frame,
        candidates=list(modules),
        modules=modules,
        max_nodes=4,
    )

    assert plan is not None
    assert len(plan.nodes) == 4
    assert plan.metadata["strategy"] == "dynamic_candidate_graph"
    assert set(plan.output_node_ids) == {node.node_id for node in plan.nodes}
    assert validate_composition_plan(plan, modules).valid


def test_open_overview_fallback_candidates_never_degrade_to_one_metric():
    from app.services import semantic_primary
    from app.services.tool_rag import RagTool, ToolSnapshot

    wanted = semantic_primary._OPEN_OVERVIEW_FALLBACK_TOOL_IDS
    snapshot = ToolSnapshot(
        tools=tuple(
            RagTool(
                tool_id=tool_id,
                kind="composite_metric",
                title=tool_id,
                description="",
                aliases=(),
                examples=(),
                required_params=(),
                dependencies=(),
                chapter_links=(),
                scenarios=(),
                shape="single_value",
            )
            for tool_id in wanted
        )
    )

    fallback = semantic_primary._open_overview_fallback_tool_ids(snapshot)

    assert len(fallback) >= 2
    assert fallback == list(wanted)


def test_cohort_followup_scenarios_stay_in_cohort_scope():
    from app.services.semantic_primary import contextual_cohort_route

    state = {"scope": "cohort", "subject": None, "scenario": None}
    assert contextual_cohort_route("哪里信号最多？", state)["domain"] == "warn"
    assert contextual_cohort_route("哪里可疑要查？", state)["domain"] == "audit"
    assert contextual_cohort_route("按行业拆风险等级", state)["domain"] == "rating"
    assert contextual_cohort_route("企业1哪里可疑？", state) is None


@pytest.mark.asyncio
async def test_open_overview_executes_dynamic_graph_and_merges_claims(monkeypatch):
    from app.services import llm_reply
    from app.services.composition_execution_bridge import execute_metric_composition
    from app.services.tool_rag import RagTool, ToolSnapshot

    @asynccontextmanager
    async def session_factory():
        yield object()

    def executor_factory(db, session_id):
        async def execute(*, params, dependency_results):
            metric = str(params["query"]).split()[0]
            return {
                "claims": [{
                    "claim": f"{metric} claim",
                    "value": {"metric": metric, "number": 1.0, "unit": ""},
                    "trace": {"table": "core_metrics", "field": metric, "query_id": metric},
                    "confidence": "computed",
                }],
                "followups": [],
            }

        return {f"metric_{name}": execute for name in ("finance_score", "tax_health_score", "invoice_score")}

    async def fake_reply(query, claims, followups, **kwargs):
        return ("综合结果", None, "llm")

    monkeypatch.setattr(llm_reply, "generate_claim_reply", fake_reply)
    tools = tuple(
        RagTool(
            tool_id=f"metric_{name}",
            kind="composite_metric",
            title=name,
            description="",
            aliases=(),
            examples=(),
            required_params=(),
            dependencies=(),
            chapter_links=(),
            scenarios=(),
            shape="single_value",
        )
        for name in ("finance_score", "tax_health_score", "invoice_score")
    )
    route = ConversationRoute(route="analysis", domain="warn", entities=["企业1"])
    frame = SemanticFrame(
        policy_route="analysis",
        task_type="open_overview",
        subject_scope="individual",
        entities=["企业1"],
    )

    out = await execute_metric_composition(
        frame=frame,
        route=route,
        policy=ConversationPolicyRegistry.resolve(route),
        query="企业1有哪些值得分析的点",
        session_id="s-open-overview",
        snapshot=ToolSnapshot(tools=tools),
        candidate_tool_ids=[tool.tool_id for tool in tools],
        session_factory=session_factory,
        executor_factory=executor_factory,
    )

    assert out is not None
    assert out.meta["composition_strategy"] == "dynamic_candidate_graph"
    assert len(out.claims) == 3
    assert len(out.plan.steps) == 3
    assert out.reply == "综合结果"


@pytest.mark.asyncio
async def test_primary_turn_routes_open_overview_into_dynamic_composition(monkeypatch):
    from app.schemas.tool_rag import ToolCandidate
    from app.services import semantic_primary

    candidates = [
        ToolCandidate(
            tool_id=f"metric_{name}",
            kind="composite_metric",
            title=name,
            description="",
            score=1.0,
        )
        for name in ("finance_score", "tax_health_score", "invoice_score")
    ]
    captured: dict[str, object] = {}

    async def fake_retrieve(*args, **kwargs):
        return candidates

    async def fake_execute(**kwargs):
        captured["candidate_tool_ids"] = kwargs.get("candidate_tool_ids")
        captured["frame"] = kwargs.get("frame")
        route = kwargs["route"]
        return semantic_primary.SemanticTurnResult(
            status="answered",
            route=route,
            policy=kwargs["policy"],
            reply="dynamic",
            meta={"composition_strategy": "dynamic_candidate_graph"},
        )

    async def fake_snapshot(_db):
        return object()

    async def fake_resolve_entities(_db, _entities):
        return ["ENT1"]

    monkeypatch.setattr(semantic_primary.session_store, "get_session", lambda _: {})
    monkeypatch.setattr(semantic_primary, "load_tool_snapshot", fake_snapshot)
    monkeypatch.setattr(semantic_primary, "resolve_enterprise_entities", fake_resolve_entities)
    monkeypatch.setattr(semantic_primary, "retrieve_tools_hybrid", fake_retrieve)
    monkeypatch.setattr(semantic_primary, "execute_metric_composition", fake_execute)

    response = await semantic_primary.run_primary_turn(
        db=object(),
        session_id="open-overview-primary",
        owner=None,
        query="企业1有哪些值得分析的点",
        raw_route={
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": ["企业1"],
            "needs_tools": True,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        persist=False,
    )

    assert captured["candidate_tool_ids"] == [item.tool_id for item in candidates]
    assert captured["frame"].entities == ["ENT1"]
    assert response["data"]["primary"]["semantic_frame"]["task_type"] == "open_overview"
    assert response["data"]["primary"]["composition_strategy"] == "dynamic_candidate_graph"
