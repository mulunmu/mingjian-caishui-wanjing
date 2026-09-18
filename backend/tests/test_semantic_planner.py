from __future__ import annotations

import pytest

from app.schemas.composition import ModuleSpec, PortSpec
from app.schemas.conversation_route import ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.semantic_plan import SemanticPlan, SemanticPlanStep
from app.services.semantic_planner import (
    semantic_plan_to_composition_plan,
    semantic_plan_to_frame,
    validate_semantic_plan,
)


def _metric_module(module_id: str, *, status: str = "validated") -> ModuleSpec:
    return ModuleSpec(
        module_id=module_id,
        kind="metric",
        version="1",
        status=status,
        inputs=[PortSpec(name="entity", data_type="entity", required=False)],
        outputs=[PortSpec(name="value", data_type="number")],
    )


def _modules() -> dict[str, ModuleSpec]:
    return {
        "metric_debt_ratio": _metric_module("metric_debt_ratio"),
        "metric_cash_flow_net": _metric_module("metric_cash_flow_net"),
    }


def _valid_plan() -> SemanticPlan:
    return SemanticPlan(
        action="analysis",
        scope="individual",
        entities=["企业1"],
        filters={"industry_l1": ["建筑"]},
        metrics=["debt_ratio", "cash_flow_net"],
        analysis_patterns=["comparison", "benchmark"],
        comparison_basis="peer",
        steps=[
            SemanticPlanStep(
                step_id="financial_1",
                tool_id="metric_debt_ratio",
                filters={"industry_l1": ["建筑"]},
                entity="企业1",
            ),
            SemanticPlanStep(
                step_id="financial_2",
                tool_id="metric_cash_flow_net",
                filters={"industry_l1": ["建筑"]},
                entity="企业1",
            ),
        ],
        confidence=0.94,
        plan_summary="同时查看资产负债率和现金流，并与建筑行业基准比较。",
    )


def test_semantic_plan_validator_accepts_executable_combinations():
    report = validate_semantic_plan(
        _valid_plan(),
        executable_tool_ids={"metric_debt_ratio", "metric_cash_flow_net"},
        modules=_modules(),
        allowed_filter_values={"industry_l1": {"建筑"}},
    )

    assert report.valid is True
    assert report.errors == []


def test_semantic_plan_validator_rejects_unknown_tool():
    plan = _valid_plan().model_copy(
        update={
            "steps": [
                SemanticPlanStep(step_id="unknown", tool_id="metric_not_real"),
            ]
        }
    )

    report = validate_semantic_plan(
        plan,
        executable_tool_ids={"metric_debt_ratio", "metric_cash_flow_net"},
        modules=_modules(),
        allowed_filter_values={"industry_l1": {"建筑"}},
    )

    assert report.valid is False
    assert any(error.code == "tool_not_executable" for error in report.errors)


def test_semantic_plan_validator_rejects_filter_value_outside_inventory():
    plan = _valid_plan().model_copy(
        update={"filters": {"industry_l1": ["不存在的行业"]}}
    )

    report = validate_semantic_plan(
        plan,
        executable_tool_ids={"metric_debt_ratio", "metric_cash_flow_net"},
        modules=_modules(),
        allowed_filter_values={"industry_l1": {"建筑"}},
    )

    assert report.valid is False
    assert any(error.code == "filter_value_not_found" for error in report.errors)


def test_non_analysis_plan_cannot_materialize_an_empty_dag():
    plan = SemanticPlan(
        action="conversation",
        scope="system",
        confidence=0.99,
        plan_summary="只是寒暄",
    )

    validated, composition = semantic_plan_to_composition_plan(
        plan, modules=_modules()
    )

    assert validated is None
    assert composition is None


def test_semantic_plan_converts_to_validated_composition_plan():
    plan, composition = semantic_plan_to_composition_plan(
        _valid_plan(), modules=_modules()
    )

    assert plan is not None
    assert composition is not None
    assert [node.module_id for node in composition.nodes] == [
        "metric_debt_ratio",
        "metric_cash_flow_net",
    ]
    assert composition.metadata["semantic_plan"] is True
    assert composition.metadata["selected_tool_ids"] == [
        "metric_debt_ratio",
        "metric_cash_flow_net",
    ]


def test_semantic_plan_replaces_regex_inferred_frame_fields():
    route = ConversationRoute(
        route="analysis",
        domain="warn",
        entities=["企业1"],
    )
    base = SemanticFrame(
        policy_route="analysis",
        task_type="metric_lookup",
        subject_scope="individual",
        entities=["企业1"],
    )

    frame = semantic_plan_to_frame(_valid_plan(), route=route, base=base)

    assert frame.metrics == ["debt_ratio", "cash_flow_net"]
    assert frame.analysis_pattern == "comparison"
    assert frame.analysis_components == ["comparison", "benchmark"]
    assert frame.comparison_basis == "peer"
    assert frame.filters["industry_l1"] == ["建筑"]


@pytest.mark.asyncio
async def test_semantic_planner_uses_llm_plan_when_valid(monkeypatch):
    from app.services import semantic_planner

    plans = [_valid_plan()]

    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return plans.pop(0)

    result = await semantic_planner.plan_semantic_turn(
        "企业1的资产负债率和现金流对比建筑业",
        route=ConversationRoute(route="analysis", entities=["企业1"]),
        candidate_tools=[
            {"tool_id": "metric_debt_ratio", "title": "资产负债率"},
            {"tool_id": "metric_cash_flow_net", "title": "现金流净额"},
        ],
        executable_tool_ids={"metric_debt_ratio", "metric_cash_flow_net"},
        modules=_modules(),
        allowed_filter_values={"industry_l1": {"建筑"}},
        completion_fn=fake_completion,
    )

    assert result.status == "ok"
    assert result.plan is not None
    assert result.composition_plan is not None
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_semantic_planner_fails_closed_after_invalid_plans(monkeypatch):
    from app.services import semantic_planner

    invalid = _valid_plan().model_copy(
        update={
            "steps": [
                SemanticPlanStep(step_id="unknown", tool_id="metric_not_real"),
            ]
        }
    )

    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return invalid

    result = await semantic_planner.plan_semantic_turn(
        "帮我随便组合一下",
        route=ConversationRoute(route="analysis"),
        candidate_tools=[],
        executable_tool_ids={"metric_debt_ratio", "metric_cash_flow_net"},
        modules=_modules(),
        allowed_filter_values={},
        completion_fn=fake_completion,
        max_attempts=2,
    )

    assert result.status == "clarify"
    assert result.plan is None
    assert result.attempts == 2
    assert result.clarification_question


@pytest.mark.asyncio
async def test_semantic_planner_normalizes_dimension_name_to_group_comparison():
    from app.services import semantic_planner

    plan = _valid_plan().model_copy(update={"comparison_basis": "industry_l1"})

    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return plan

    result = await semantic_planner.plan_semantic_turn(
        "制造业和服务业对比",
        route=ConversationRoute(route="analysis"),
        candidate_tools=[],
        executable_tool_ids={"metric_debt_ratio", "metric_cash_flow_net"},
        modules=_modules(),
        allowed_filter_values={"industry_l1": {"建筑"}},
        completion_fn=fake_completion,
    )

    assert result.status == "ok"
    assert result.plan is not None
    assert result.plan.comparison_basis == "cohort_slice"
