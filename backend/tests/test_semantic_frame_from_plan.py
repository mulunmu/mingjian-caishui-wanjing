from __future__ import annotations

from app.schemas.conversation_route import ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.semantic_plan import SemanticPlan, SemanticPlanStep
from app.services.semantic_frame_from_plan import frame_from_plan
from app.services.semantic_planner import semantic_plan_to_frame


def _plan() -> SemanticPlan:
    return SemanticPlan(
        action="analysis",
        scope="individual",
        entities=["企业1"],
        filters={"industry_l1": ["建筑"]},
        metrics=["debt_ratio", "cash_flow_net"],
        analysis_patterns=["comparison", "benchmark"],
        comparison_basis="peer",
        steps=[
            SemanticPlanStep(step_id="s1", tool_id="metric_debt_ratio"),
            SemanticPlanStep(step_id="s2", tool_id="metric_cash_flow_net"),
        ],
        output_requirements=["reply", "claims"],
        confidence=0.93,
    )


def test_frame_from_plan_uses_plan_metrics_patterns_and_filters():
    route = ConversationRoute(
        route="analysis",
        domain="warn",
        entities=["企业1"],
    )
    base = SemanticFrame(
        policy_route="analysis",
        task_type="metric_lookup",
        subject_scope="unbound",
        metrics=[],
    )

    frame = frame_from_plan(_plan(), route=route, base=base)

    assert frame.task_type == "comparison"
    assert frame.analysis_pattern == "comparison"
    assert frame.analysis_components == ["comparison", "benchmark"]
    assert frame.comparison_basis == "peer"
    assert frame.subject_scope == "individual"
    assert frame.entities == ["企业1"]
    assert frame.metrics == ["debt_ratio", "cash_flow_net"]
    assert frame.filters["industry_l1"] == ["建筑"]
    assert frame.confidence == 0.93


def test_semantic_planner_wrapper_delegates_to_frame_from_plan():
    route = ConversationRoute(route="analysis", entities=["企业1"])
    base = SemanticFrame(policy_route="analysis", entities=["企业1"])

    wrapped = semantic_plan_to_frame(_plan(), route=route, base=base)
    direct = frame_from_plan(_plan(), route=route, base=base)

    assert wrapped.model_dump() == direct.model_dump()
