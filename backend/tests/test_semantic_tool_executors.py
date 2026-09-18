from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.schemas.conversation_route import ConversationPolicy
from app.schemas.semantic_query import QueryType, SemanticQuery
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.plan_execution import PlanValidationError, execute_tool_plan_async
from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.semantic_tool_executors import (
    build_semantic_tool_executors,
    semantic_executor_tool_ids,
)
from app.services.tool_rag import load_tool_snapshot_sync
from tests.test_semantic_registry_seed import _engine


def _snapshot():
    engine = _engine()
    seed_semantic_registry(engine)
    return load_tool_snapshot_sync(engine)


def _policy() -> ConversationPolicy:
    return ConversationPolicy(
        response_mode="analysis",
        retrieve_candidates=True,
        execute_tools=True,
        allow_analysis=True,
    )


def test_numeric_core_metric_is_supported():
    assert "metric_debt_ratio" in semantic_executor_tool_ids()
    assert "metric_tax_arrears_cnt" in semantic_executor_tool_ids()


def test_resolved_opaque_entity_is_forwarded_to_semantic_query():
    from app.services.semantic_tool_executors import _build_semantic_query

    sq = _build_semantic_query(
        "debt_ratio",
        {"entity": "0039fa8febbd8593f36ec19219685382", "query": "企业1资产负债率"},
    )
    assert sq.entities == ["0039fa8febbd8593f36ec19219685382"]


@pytest.mark.asyncio
async def test_metric_dispatcher_passes_entity_scope_to_builder(monkeypatch):
    captured: dict = {}

    async def fake_authenticity(
        db,
        industry_l1=None,
        *,
        province=None,
        enterprise_ids=None,
    ):
        captured["enterprise_ids"] = enterprise_ids
        return [], {}

    from app.services import judgment_service

    monkeypatch.setattr(
        judgment_service,
        "build_authenticity_claims",
        fake_authenticity,
    )
    sq = SemanticQuery(
        query_type=QueryType.lookup,
        metrics=["authenticity_score"],
        entities=["0039fa8febbd8593f36ec19219685382"],
        source="corrected",
    )

    await judgment_service._metric_dispatcher(object(), sq, "authenticity_score")

    assert captured["enterprise_ids"] == ["0039fa8febbd8593f36ec19219685382"]


@pytest.mark.asyncio
async def test_metric_executor_builds_semantic_query_and_returns_claims(monkeypatch):
    captured: dict = {}

    async def fake_run_semantic_query(db, sq, session_id):
        captured["sq"] = sq
        captured["session_id"] = session_id
        return (
            [
                Claim(
                    claim="样本资产负债率 72.00。",
                    value=ClaimValue(metric="debt_ratio", number=72.0, unit="%"),
                    trace=ClaimTrace(
                        table="core_metrics",
                        field="debt_ratio",
                        query_id="Q_test",
                    ),
                    confidence="computed",
                )
            ],
            ["继续看现金流"],
            {"function": "score", "dimension": "overall", "query_type": "lookup"},
        )

    from app.services import judgment_service

    monkeypatch.setattr(judgment_service, "run_semantic_query", fake_run_semantic_query)
    executors = build_semantic_tool_executors(db=object(), session_id="session-1")
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="debt",
                tool_id="metric_debt_ratio",
                params={
                    "entity": "ENT017",
                    "industry_l1": "制造",
                    "province": "广东",
                },
            )
        ],
    )
    result = await execute_tool_plan_async(
        plan,
        _snapshot(),
        executors,
        policy=_policy(),
    )
    sq = captured["sq"]
    assert sq.metrics == ["debt_ratio"]
    assert sq.filters == {"industry_l1": ["制造"], "province": ["广东"]}
    assert sq.entities == ["ENT017"]
    assert captured["session_id"] == "session-1"
    assert result.claims[0]["value"]["metric"] == "debt_ratio"


def test_every_snapshot_metric_tool_has_an_executor():
    snapshot = _snapshot()
    registered = semantic_executor_tool_ids()
    metric_tool_ids = {tool.tool_id for tool in snapshot.tools if tool.tool_id.startswith("metric_")}

    assert metric_tool_ids <= registered
