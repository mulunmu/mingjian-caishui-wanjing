from __future__ import annotations

import pytest

from app.schemas.conversation_route import ConversationPolicy
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.plan_execution import (
    PlanValidationError,
    execute_tool_plan_async,
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


@pytest.mark.asyncio
async def test_async_plan_executes_deterministically():
    async def debt(**kwargs):
        return {"metric": "debt_ratio", "value": 0.72}

    async def cash(**kwargs):
        return {"metric": "cash_flow_level", "value": "承压"}

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
    first = await execute_tool_plan_async(
        plan,
        _snapshot(),
        {
            "metric_debt_ratio": debt,
            "metric_cash_flow_level": cash,
        },
        policy=_allow_policy(),
    )
    second = await execute_tool_plan_async(
        plan,
        _snapshot(),
        {
            "metric_debt_ratio": debt,
            "metric_cash_flow_level": cash,
        },
        policy=_allow_policy(),
    )
    assert first == second
    assert [claim["metric"] for claim in first.claims] == [
        "debt_ratio",
        "cash_flow_level",
    ]


@pytest.mark.asyncio
async def test_invalid_async_plan_never_calls_tool():
    called = False

    async def should_not_run(**kwargs):
        nonlocal called
        called = True
        return {}

    plan = ToolPlan(
        mode="answer",
        steps=[ToolStep(step_id="x", tool_id="metric_missing", params={})],
    )
    with pytest.raises(PlanValidationError):
        await execute_tool_plan_async(
            plan,
            _snapshot(),
            {"metric_missing": should_not_run},
            policy=_allow_policy(),
        )
    assert called is False