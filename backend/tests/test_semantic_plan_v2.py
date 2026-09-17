from __future__ import annotations

from app.schemas.composition import ModuleSpec, PortSpec
from app.schemas.semantic_action import SemanticAction
from app.schemas.semantic_plan import SemanticPlan, SemanticPlanStep, SemanticReference
from app.services.semantic_planner import semantic_plan_to_composition_plan


def _modules():
    return {
        "metric_debt_ratio": ModuleSpec(
            module_id="metric_debt_ratio",
            kind="metric",
            version="1",
            status="validated",
            inputs=[PortSpec(name="entity", data_type="entity", required=False)],
            outputs=[PortSpec(name="value", data_type="number")],
        )
    }


def test_semantic_plan_v2_defaults_and_typed_action():
    plan = SemanticPlan(
        action=SemanticAction.ANALYSIS,
        metrics=["debt_ratio"],
        steps=[
            SemanticPlanStep(step_id="s1", tool_id="metric_debt_ratio"),
        ],
        confidence=0.9,
    )

    assert plan.action is SemanticAction.ANALYSIS
    assert plan.planner_version == "semantic-plan-v2"
    assert plan.route_hint is None
    assert plan.policy_tags == []
    assert plan.requires_confirmation is False
    assert plan.resolved_references == []
    assert plan.report_plan is None
    assert plan.ambiguity_reason is None
    assert plan.repair_history == []


def test_semantic_plan_accepts_structured_references_and_report_plan():
    plan = SemanticPlan(
        action="analysis",
        metrics=["debt_ratio"],
        steps=[SemanticPlanStep(step_id="s1", tool_id="metric_debt_ratio")],
        confidence=0.9,
        resolved_references=[
            {"kind": "topic", "ref_id": "topic-4", "label": "上上个问题", "score": 0.94}
        ],
        report_plan={"report_mode": "custom", "chapters": []},
    )

    assert isinstance(plan.resolved_references[0], SemanticReference)
    assert plan.resolved_references[0].ref_id == "topic-4"
    assert plan.report_plan == {"report_mode": "custom", "chapters": []}


def test_inventory_action_alias_normalizes_to_metadata_query():
    plan = SemanticPlan(
        action="inventory",
        steps=[],
        confidence=0.9,
    )

    assert plan.action is SemanticAction.METADATA_QUERY


def test_route_hint_never_changes_tool_selection():
    plan = SemanticPlan(
        action="analysis",
        route_hint="report",
        metrics=["debt_ratio"],
        steps=[
            SemanticPlanStep(step_id="s1", tool_id="metric_debt_ratio"),
        ],
        analysis_patterns=["metric_lookup"],
        confidence=0.9,
    )

    validated, composition = semantic_plan_to_composition_plan(
        plan,
        modules=_modules(),
        executable_tool_ids={"metric_debt_ratio"},
    )

    assert validated is not None
    assert composition is not None
    assert [node.module_id for node in composition.nodes] == ["metric_debt_ratio"]
