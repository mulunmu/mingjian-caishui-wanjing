from __future__ import annotations

import pytest

from app.schemas.composition import CompositionPlan, ModuleSpec, PortSpec
from app.schemas.semantic_plan import SemanticPlan, SemanticPlanStep
from app.services.semantic_planner import SemanticPlanningResult


def _module(tool_id: str) -> ModuleSpec:
    return ModuleSpec(
        module_id=tool_id,
        kind="metric",
        version="1",
        status="validated",
        inputs=[PortSpec(name="entity", data_type="entity", required=False)],
        outputs=[PortSpec(name="value", data_type="number")],
    )


class _Snapshot:
    tools = ()


async def _snapshot_loader(_db):
    return _Snapshot()


async def _inventory_loader(_db, top_n=1):
    del top_n
    return {
        "industries": [{"industry_l1": "制造", "n": 1}],
        "provinces": [{"province": "广东", "n": 1}],
        "cities": [{"city": "深圳", "n": 1}],
    }


def _catalog(_snapshot):
    return {"metric_debt_ratio": _module("metric_debt_ratio")}


@pytest.mark.asyncio
async def test_semantic_planner_node_skips_when_feature_disabled(monkeypatch):
    from app.services import semantic_nodes

    monkeypatch.setattr(semantic_nodes, "semantic_planner_enabled", lambda: False)
    result = await semantic_nodes.semantic_planner_node(
        db=object(),
        query="企业1有哪些值得分析的点",
        raw_route={"route": "analysis", "entities": ["企业1"]},
        snapshot_loader=_snapshot_loader,
        inventory_loader=_inventory_loader,
        catalog_builder=_catalog,
    )

    assert result["planner_status"] == "disabled_or_unavailable"
    assert result["semantic_plan"] is None


@pytest.mark.asyncio
async def test_semantic_planner_fails_closed_without_legacy_fallback(monkeypatch):
    from app.services import semantic_nodes

    monkeypatch.setattr(
        semantic_nodes, "semantic_planner_langgraph_node_enabled", lambda: False
    )
    monkeypatch.setattr(
        semantic_nodes, "semantic_legacy_route_fallback_enabled", lambda: False
    )
    result = await semantic_nodes.semantic_planner_node(
        db=object(),
        session_id="session-1",
        query="分析企业1",
        raw_route={"route": "analysis", "entities": ["企业1"]},
    )

    assert result["planner_status"] == "clarify"
    assert result["semantic_plan"] is None
    assert result["planner_errors"] == [
        "semantic_planner_unavailable_without_legacy_route_fallback"
    ]


def test_report_planner_respects_feature_flag(monkeypatch):
    from app.services import semantic_nodes

    monkeypatch.setattr(semantic_nodes, "semantic_report_plan_enabled", lambda: False)
    result = semantic_nodes.report_planner_node({"data": {"primary": {"route": "report"}}})

    assert result["report_plan_status"] == "disabled"


@pytest.mark.asyncio
async def test_semantic_planner_node_returns_plan_and_composition(monkeypatch):
    from app.services import semantic_nodes

    plan = SemanticPlan(
        action="analysis",
        scope="individual",
        entities=["企业1"],
        metrics=["debt_ratio"],
        analysis_patterns=["metric_lookup"],
        steps=[SemanticPlanStep(step_id="s1", tool_id="metric_debt_ratio")],
        confidence=0.95,
        plan_summary="查看企业1资产负债率",
    )
    composition = CompositionPlan(
        plan_id="plan-test",
        nodes=[],
        output_node_ids=[],
        metadata={"semantic_plan": True},
    )

    async def planner(**_kwargs):
        return SemanticPlanningResult(
            status="ok",
            plan=plan,
            composition_plan=composition,
            attempts=1,
        )

    monkeypatch.setattr(semantic_nodes, "semantic_planner_enabled", lambda: True)
    monkeypatch.setattr(semantic_nodes.llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(semantic_nodes, "plan_semantic_turn", planner)

    result = await semantic_nodes.semantic_planner_node(
        db=object(),
        query="企业1有哪些值得分析的点",
        raw_route={
            "route": "analysis",
            "domain": "general",
            "entities": ["企业1"],
            "needs_tools": True,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        snapshot_loader=_snapshot_loader,
        inventory_loader=_inventory_loader,
        catalog_builder=_catalog,
    )

    assert result["planner_status"] == "ok"
    assert result["semantic_plan"]["plan_summary"] == "查看企业1资产负债率"
    assert result["composition_plan"]["plan_id"] == "plan-test"
    assert result["semantic_candidate_tool_ids"] == ["metric_debt_ratio"]


@pytest.mark.asyncio
async def test_semantic_planner_runs_for_misclassified_out_of_domain(monkeypatch):
    from app.services import semantic_nodes

    plan = SemanticPlan(
        action="analysis",
        scope="cohort",
        metrics=["invoice_score"],
        analysis_patterns=["anomaly"],
        steps=[SemanticPlanStep(step_id="s1", tool_id="metric_invoice_score")],
        confidence=0.95,
        plan_summary="分析发票异常",
    )

    async def planner(**_kwargs):
        return SemanticPlanningResult(status="ok", plan=plan, composition_plan=None, attempts=1)

    monkeypatch.setattr(semantic_nodes, "semantic_planner_enabled", lambda: True)
    monkeypatch.setattr(semantic_nodes.llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(semantic_nodes, "plan_semantic_turn", planner)

    result = await semantic_nodes.semantic_planner_node(
        db=object(),
        query="换成发票异常",
        raw_route={"route": "out_of_domain", "domain": None, "entities": []},
        snapshot_loader=_snapshot_loader,
        inventory_loader=_inventory_loader,
        catalog_builder=_catalog,
    )

    assert result["planner_status"] == "ok"
    assert result["semantic_plan"]["action"] == "analysis"


@pytest.mark.asyncio
async def test_semantic_planner_replans_non_analysis_during_active_session(monkeypatch):
    from app.services import semantic_nodes

    conversation = SemanticPlan(action="conversation", scope="cohort", confidence=0.9)
    analysis = SemanticPlan(
        action="analysis",
        scope="cohort",
        filters={"industry_l1": ["制造"]},
        metrics=["invoice_score"],
        analysis_patterns=["anomaly"],
        steps=[SemanticPlanStep(step_id="s1", tool_id="metric_invoice_score")],
        confidence=0.95,
    )
    calls = []

    async def planner(**kwargs):
        calls.append(kwargs["session_context"])
        plan = conversation if len(calls) == 1 else analysis
        return SemanticPlanningResult(status="ok", plan=plan, composition_plan=None, attempts=1)

    monkeypatch.setattr(semantic_nodes, "semantic_planner_enabled", lambda: True)
    monkeypatch.setattr(semantic_nodes.llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(semantic_nodes, "plan_semantic_turn", planner)

    result = await semantic_nodes.semantic_planner_node(
        db=object(),
        query="换成发票异常",
        raw_route={"route": "out_of_domain", "domain": None, "entities": []},
        memory_context={
            "dialogue_state": {
                "scope": "cohort",
                "analysis_focus": {"industry_l1": "制造"},
            }
        },
        snapshot_loader=_snapshot_loader,
        inventory_loader=_inventory_loader,
        catalog_builder=_catalog,
    )

    assert len(calls) == 2
    assert calls[1]["analysis_continuation_required"] is True
    assert result["semantic_plan"]["action"] == "analysis"


@pytest.mark.asyncio
async def test_plan_validator_node_rejects_unknown_tool():
    from app.services import semantic_nodes

    plan = SemanticPlan(
        action="analysis",
        scope="individual",
        entities=["企业1"],
        metrics=["not_real"],
        analysis_patterns=["metric_lookup"],
        steps=[SemanticPlanStep(step_id="s1", tool_id="metric_not_real")],
        confidence=0.95,
    )

    result = await semantic_nodes.plan_validator_node(
        db=object(),
        semantic_plan=plan.model_dump(mode="json"),
        snapshot_loader=_snapshot_loader,
        inventory_loader=_inventory_loader,
        catalog_builder=_catalog,
    )

    assert result["planner_status"] == "clarify"
    assert any("not executable" in item for item in result["planner_errors"])
    assert result["composition_plan"] is None


@pytest.mark.asyncio
async def test_plan_validator_accepts_non_analysis_plan_without_composition():
    from app.services import semantic_nodes

    plan = SemanticPlan(
        action="conversation",
        scope="system",
        confidence=0.95,
        plan_summary="普通寒暄",
    )

    result = await semantic_nodes.plan_validator_node(
        db=object(),
        semantic_plan=plan.model_dump(mode="json"),
        snapshot_loader=_snapshot_loader,
        inventory_loader=_inventory_loader,
        catalog_builder=_catalog,
    )

    assert result["planner_status"] == "ok"
    assert result["composition_plan"] is None


def test_langgraph_contains_semantic_planning_stages():
    pytest.importorskip("langgraph")
    from app.services import outer_orchestrator

    runtime = outer_orchestrator.OuterTurnRuntime(
        db=object(),
        session_id="graph-contract",
        owner=None,
        enterprise_id=None,
        user=None,
    )
    graph, _command = outer_orchestrator._compile_graph(
        runtime,
        require_approval=False,
    )
    diagram = graph.compile().get_graph()
    edges = {(edge.source, edge.target) for edge in diagram.edges}

    assert ("classify", "semantic_planner") in edges
    assert ("semantic_planner", "capability_retrieval") in edges
    assert ("capability_retrieval", "plan_validator") in edges
    assert ("plan_validator", "plan_repair") in edges
    assert ("plan_repair", "planning") in edges
    assert ("execute", "evidence_critic") in edges
    assert ("evidence_critic", "finance_review") in edges
    assert ("finance_review", "report_planner") in edges
    assert ("report_planner", "response_composer") in edges
    assert ("response_composer", "final_guard") in edges


@pytest.mark.asyncio
async def test_plan_repair_node_normalizes_filter_aliases():
    from app.services import semantic_nodes

    plan = SemanticPlan(
        action="analysis",
        scope="cohort",
        filters={"industry_l1": ["制造业"]},
        metrics=["debt_ratio"],
        analysis_patterns=["comparison"],
        comparison_basis="cohort_slice",
        steps=[
            SemanticPlanStep(
                step_id="s1",
                tool_id="metric_debt_ratio",
                filters={"industry_l1": ["制造业"]},
            )
        ],
        confidence=0.95,
    )

    result = await semantic_nodes.plan_repair_node(
        db=object(),
        semantic_plan=plan.model_dump(mode="json"),
        planner_errors=["industry_l1=制造业 is not present in the data inventory"],
        snapshot_loader=_snapshot_loader,
        inventory_loader=_inventory_loader,
        catalog_builder=_catalog,
    )

    assert result["repair_status"] == "repaired"
    assert result["semantic_plan"]["filters"]["industry_l1"] == ["制造"]
    assert result["planner_status"] == "ok"


def test_evidence_critic_flags_analysis_without_claims():
    from app.services import semantic_nodes

    result = semantic_nodes.evidence_critic_node(
        {
            "reply": "分析完成",
            "data": {
                "primary": {"route": "analysis", "status": "answered", "fallback": False},
                "claims": [],
            },
        }
    )

    assert result["evidence_critic_status"] == "failed"
    assert "analysis_without_claims" in result["evidence_critic_issues"]


def test_response_composer_preserves_claim_backed_reply():
    from app.services import semantic_nodes

    payload = {
        "reply": "资产负债率偏高。",
        "data": {
            "primary": {"route": "analysis", "status": "answered", "fallback": False},
            "claims": [
                {
                    "claim": "资产负债率偏高。",
                    "trace": {"table": "core_metrics", "field": "debt_ratio"},
                }
            ],
        },
    }

    result = semantic_nodes.response_composer_node(payload)

    assert result["result"]["reply"] == "资产负债率偏高。"
    assert result["response_composer_status"] == "completed"


@pytest.mark.asyncio
async def test_runtime_execute_passes_precomputed_plan_to_primary(monkeypatch):
    pytest.importorskip("pgvector")
    from app.services import outer_orchestrator, semantic_primary

    captured: dict = {}

    async def primary(**kwargs):
        captured.update(kwargs)
        return {"reply": "ok", "session_id": kwargs["session_id"], "data": {}}

    monkeypatch.setattr(semantic_primary, "run_primary_turn", primary)
    runtime = outer_orchestrator.OuterTurnRuntime(
        db=object(),
        session_id="runtime-plan-contract",
        owner=None,
        enterprise_id=None,
        user=None,
    )
    await runtime.execute(
        "企业1有哪些值得分析的点",
        {"route": "analysis", "entities": ["企业1"]},
        semantic_plan={"action": "analysis", "confidence": 0.9},
        composition_plan={"plan_id": "plan-1", "nodes": [], "edges": []},
        planner_meta={"status": "ok", "attempts": 1, "errors": []},
    )

    assert captured["semantic_plan"]["action"] == "analysis"
    assert captured["composition_plan"]["plan_id"] == "plan-1"
    assert captured["planner_meta"]["status"] == "ok"
