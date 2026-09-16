from __future__ import annotations

import pytest

from app.schemas.conversation_route import ConversationPolicy
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.plan_execution import (
    PlanValidationError,
    execute_tool_plan,
    validate_tool_plan,
)
from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.tool_rag import load_tool_snapshot_sync
from tests.test_semantic_registry_seed import _engine


def _snapshot():
    engine = _engine()
    seed_semantic_registry(engine)
    return load_tool_snapshot_sync(engine)


def _allow_policy() -> ConversationPolicy:
    return ConversationPolicy(
        response_mode="analysis",
        retrieve_candidates=True,
        execute_tools=True,
        allow_analysis=True,
    )


def _tool_fns():
    return {
        "metric_debt_ratio": lambda **_: {"metric": "debt_ratio", "value": 0.72},
        "metric_cash_flow_level": lambda **_: {
            "metric": "cash_flow_level",
            "value": "承压",
        },
    }


def test_valid_plan_executes_deterministically():
    snapshot = _snapshot()
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="debt",
                tool_id="metric_debt_ratio",
                params={"entity": "ENT017"},
            ),
            ToolStep(
                step_id="cash",
                tool_id="metric_cash_flow_level",
                params={"entity": "ENT017"},
                depends_on=["debt"],
            ),
        ],
    )
    first = execute_tool_plan(plan, snapshot, _tool_fns(), policy=_allow_policy())
    second = execute_tool_plan(plan, snapshot, _tool_fns(), policy=_allow_policy())
    assert first == second
    assert first.claims == [
        {"metric": "debt_ratio", "value": 0.72},
        {"metric": "cash_flow_level", "value": "承压"},
    ]


def test_unknown_tool_is_rejected():
    plan = ToolPlan(
        mode="answer",
        steps=[ToolStep(step_id="x", tool_id="metric_missing", params={})],
    )
    with pytest.raises(PlanValidationError, match="unknown tool"):
        validate_tool_plan(plan, _snapshot(), policy=_allow_policy())


def test_missing_required_param_is_rejected():
    plan = ToolPlan(
        mode="answer",
        steps=[ToolStep(step_id="x", tool_id="metric_debt_ratio", params={})],
    )
    with pytest.raises(PlanValidationError, match="missing params"):
        validate_tool_plan(plan, _snapshot(), policy=_allow_policy())


def test_missing_explicit_dependency_is_rejected():
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="x",
                tool_id="metric_debt_ratio",
                params={"entity": "ENT017"},
                depends_on=["missing"],
            )
        ],
    )
    with pytest.raises(PlanValidationError, match="missing dependency"):
        validate_tool_plan(plan, _snapshot(), policy=_allow_policy())


def test_cycle_is_rejected():
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="a",
                tool_id="metric_debt_ratio",
                params={"entity": "ENT017"},
                depends_on=["b"],
            ),
            ToolStep(
                step_id="b",
                tool_id="metric_cash_flow_level",
                params={"entity": "ENT017"},
                depends_on=["a"],
            ),
        ],
    )
    with pytest.raises(PlanValidationError, match="cycle"):
        validate_tool_plan(plan, _snapshot(), policy=_allow_policy())


def test_policy_without_execution_rejects_plan():
    denied = ConversationPolicy(
        response_mode="clarify",
        retrieve_candidates=True,
        execute_tools=False,
        allow_analysis=True,
    )
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="x",
                tool_id="metric_debt_ratio",
                params={"entity": "ENT017"},
            )
        ],
    )
    with pytest.raises(PlanValidationError, match="does not allow"):
        validate_tool_plan(plan, _snapshot(), policy=denied)


def test_invalid_plan_never_calls_executor():
    called = False

    def should_not_run(**_):
        nonlocal called
        called = True
        return {}

    plan = ToolPlan(
        mode="answer",
        steps=[ToolStep(step_id="x", tool_id="metric_missing", params={})],
    )
    with pytest.raises(PlanValidationError):
        execute_tool_plan(
            plan,
            _snapshot(),
            {"metric_missing": should_not_run},
            policy=_allow_policy(),
        )
    assert called is False
