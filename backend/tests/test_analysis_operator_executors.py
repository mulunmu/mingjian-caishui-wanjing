from __future__ import annotations

import pytest

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.analysis_operator_executors import build_analysis_operator_executors
from app.services.semantic_tool_executors import semantic_executor_tool_ids
from app.schemas.composition import ModuleSpec, PortSpec
from app.schemas.semantic_plan import SemanticPlan, SemanticPlanStep
from app.services.semantic_planner import semantic_plan_to_composition_plan


def _claim(metric: str, number: float, unit: str = "") -> Claim:
    return Claim(
        claim=f"{metric}={number}{unit}",
        value=ClaimValue(metric=metric, number=number, unit=unit),
        trace=ClaimTrace(table="test", field=metric, query_id=f"Q_{metric}"),
        confidence="computed",
    )


@pytest.mark.asyncio
async def test_operator_summary_returns_claim_without_new_number():
    executors = build_analysis_operator_executors(db=object(), session_id="s1")
    result = await executors["operator_summary"](
        params={"claims": [_claim("debt_ratio", 80, "%").model_dump()]},
        dependency_results={},
    )

    assert result["claims"][0]["value"]["metric"] == "operator_summary"
    assert "debt_ratio" in result["claims"][0]["claim"]


@pytest.mark.asyncio
async def test_operator_rank_selects_highest_number():
    executors = build_analysis_operator_executors(db=object(), session_id="s1")
    result = await executors["operator_rank"](
        params={
            "claims": [
                _claim("debt_ratio", 80, "%").model_dump(),
                _claim("net_margin", -10, "%").model_dump(),
            ]
        },
        dependency_results={},
    )

    assert len(result["claims"]) == 1
    assert "80" in result["claims"][0]["claim"]
    assert result["claims"][0]["value"]["metric"] == "operator_rank"


@pytest.mark.asyncio
async def test_operator_change_rate_computes_from_two_claims():
    executors = build_analysis_operator_executors(db=object(), session_id="s1")
    result = await executors["operator_change_rate"](
        params={
            "claims": [
                _claim("revenue", 100, "万元").model_dump(),
                _claim("revenue", 120, "万元").model_dump(),
            ]
        },
        dependency_results={},
    )

    assert len(result["claims"]) == 1
    assert result["claims"][0]["value"]["number"] == 20.0
    assert result["claims"][0]["value"]["unit"] == "%"


@pytest.mark.asyncio
async def test_operator_proportion_uses_claim_total():
    executors = build_analysis_operator_executors(db=object(), session_id="s1")
    result = await executors["operator_proportion"](
        params={
            "claims": [
                _claim("manufacturing", 25, "家").model_dump(),
                _claim("services", 75, "家").model_dump(),
            ]
        },
        dependency_results={},
    )

    assert len(result["claims"]) == 1
    assert "25.0%" in result["claims"][0]["claim"]
    assert "75.0%" in result["claims"][0]["claim"]


def test_operator_ids_are_executable_planner_capabilities():
    executable = semantic_executor_tool_ids()
    assert "operator_summary" in executable
    assert "operator_rank" in executable
    assert "operator_change_rate" in executable
    assert "operator_proportion" in executable


def test_plan_can_compose_metric_into_dependent_operator():
    modules = {
        "metric_debt_ratio": ModuleSpec(
            module_id="metric_debt_ratio",
            kind="metric",
            version="1",
            status="validated",
            inputs=[PortSpec(name="entity", data_type="entity", required=False)],
            outputs=[
                PortSpec(name="value", data_type="number"),
                PortSpec(name="claims", data_type="claims"),
            ],
        ),
        "operator_summary": ModuleSpec(
            module_id="operator_summary",
            kind="operator",
            version="1",
            status="validated",
            inputs=[PortSpec(name="claims", data_type="claims", required=False)],
            outputs=[PortSpec(name="claims", data_type="claims")],
        ),
    }
    plan = SemanticPlan(
        action="analysis",
        metrics=["debt_ratio"],
        analysis_patterns=["drilldown"],
        steps=[
            SemanticPlanStep(step_id="s1", tool_id="metric_debt_ratio"),
            SemanticPlanStep(
                step_id="s2",
                tool_id="operator_summary",
                depends_on=["s1"],
            ),
        ],
        confidence=0.95,
    )

    validated, composition = semantic_plan_to_composition_plan(
        plan,
        modules=modules,
        executable_tool_ids={"metric_debt_ratio", "operator_summary"},
    )

    assert validated is not None
    assert composition is not None
    assert len(composition.edges) == 1
    assert composition.edges[0].from_node == "s1"
    assert composition.edges[0].to_node == "s2"
