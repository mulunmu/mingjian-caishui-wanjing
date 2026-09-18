from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.services.composition_execution_bridge import execute_metric_composition
from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.composition_execution_bridge import (
    _comparison_claims_from_semantic_nodes,
)
from app.services.tool_rag import RagTool, ToolSnapshot


def _snapshot():
    return ToolSnapshot(
        tools=(
            RagTool(
                tool_id="metric_debt_ratio", kind="atomic_metric", title="资产负债率",
                description="", aliases=(), examples=(), required_params=(), dependencies=(),
                chapter_links=(), scenarios=(), shape="single_value",
            ),
            RagTool(
                tool_id="metric_cash_flow_net", kind="atomic_metric", title="现金流净额",
                description="", aliases=(), examples=(), required_params=(), dependencies=(),
                chapter_links=(), scenarios=(), shape="single_value",
            ),
        )
    )


@pytest.mark.asyncio
async def test_execute_metric_composition_merges_parallel_claims(monkeypatch):
    @asynccontextmanager
    async def session_factory():
        yield object()

    def executor_factory(db, session_id):
        async def execute(*, params, dependency_results):
            if "debt" in params["query"]:
                metric, number, unit, qid = "debt_ratio", 80.0, "%", "Q1"
            else:
                metric, number, unit, qid = "cash_flow_net", -10.0, "元", "Q2"
            return {
                "claims": [{
                    "claim": f"{metric} claim",
                    "value": {"metric": metric, "number": number, "unit": unit},
                    "trace": {"table": "core_metrics", "field": metric, "query_id": qid},
                    "confidence": "computed",
                }],
                "followups": [f"continue-{metric}"],
                "meta": {
                    "charts": {
                        "type": "bar",
                        "data": {"labels": ["A"], "series": [{"name": metric, "values": [1]}]},
                    }
                },
            }

        return {"metric_debt_ratio": execute, "metric_cash_flow_net": execute}

    async def fake_reply(query, claims, followups, **kwargs):
        return ("已合并两项指标", None, "llm")

    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "generate_claim_reply", fake_reply)
    route = ConversationRoute(route="analysis", domain="loan", entities=["ENT1"])
    frame = SemanticFrame(
        policy_route="analysis", business_domain="loan", task_type="multi_metric",
        subject_scope="individual", entities=["ENT1"], metrics=["debt_ratio", "cash_flow_net"],
    )
    out = await execute_metric_composition(
        frame=frame, route=route, policy=ConversationPolicyRegistry.resolve(route),
        query="企业1资产负债率和现金流怎么样", session_id="s1", snapshot=_snapshot(),
        session_factory=session_factory, executor_factory=executor_factory, max_concurrency=2,
    )
    assert out is not None
    assert out.status == "answered"
    assert len(out.claims) == 2
    assert out.meta["composition_plan_id"].startswith("plan-multi-metric")
    assert out.meta["composition_total_cost"] == 2.0
    assert out.reply == "已合并两项指标"
    assert out.meta["charts"][0]["type"] == "bar"


@pytest.mark.asyncio
async def test_execute_metric_composition_returns_none_for_single_metric():
    route = ConversationRoute(route="analysis", domain="loan")
    frame = SemanticFrame(
        policy_route="analysis", business_domain="loan", task_type="metric_lookup",
        metrics=["debt_ratio"],
    )
    out = await execute_metric_composition(
        frame=frame, route=route, policy=ConversationPolicyRegistry.resolve(route),
        query="资产负债率", session_id="s1", snapshot=_snapshot(),
        session_factory=None, executor_factory=None,
    )
    assert out is None


@pytest.mark.asyncio
async def test_execute_metric_composition_keeps_partial_results(monkeypatch):
    @asynccontextmanager
    async def session_factory():
        yield object()

    def executor_factory(db, session_id):
        async def good(*, params, dependency_results):
            return {
                "claims": [{
                    "claim": "good",
                    "value": {"metric": "debt_ratio", "number": 1, "unit": "%"},
                    "trace": {"table": "core_metrics", "field": "debt_ratio", "query_id": "Q1"},
                    "confidence": "computed",
                }],
                "followups": [],
            }

        async def bad(*, params, dependency_results):
            raise RuntimeError("node failed")

        return {"metric_debt_ratio": good, "metric_cash_flow_net": bad}

    async def fake_reply(query, claims, followups, **kwargs):
        return ("partial", None, "llm")

    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "generate_claim_reply", fake_reply)
    route = ConversationRoute(route="analysis", domain="loan", entities=["ENT1"])
    frame = SemanticFrame(
        policy_route="analysis", business_domain="loan", task_type="multi_metric",
        subject_scope="individual", entities=["ENT1"], metrics=["debt_ratio", "cash_flow_net"],
    )
    out = await execute_metric_composition(
        frame=frame, route=route, policy=ConversationPolicyRegistry.resolve(route),
        query="组合", session_id="s-partial", snapshot=_snapshot(),
        session_factory=session_factory, executor_factory=executor_factory,
    )
    assert out is not None
    assert len(out.claims) == 1
    assert out.meta["composition_failed_nodes"]


def test_semantic_node_comparison_builds_cross_group_claim():
    claims = []
    for group, number in (("制造", 52), ("IT软件", 11)):
        claims.append(
            Claim(
                claim=f"{group} suspicious_count {number}",
                value=ClaimValue(metric="suspicious_count", number=number, unit="家"),
                trace=ClaimTrace(table="core_metrics", field="suspicious_count", query_id="Q"),
                confidence="computed",
                evidence_chain=[f"semantic_group_industry_l1={group}"],
            )
        )

    out = _comparison_claims_from_semantic_nodes(
        claims,
        group_by="industry_l1",
        groups=["制造", "IT软件"],
    )

    assert len(out) == 1
    assert out[0].value is not None
    assert out[0].value.metric == "compare_suspicious_count"
    assert "制造 52家" in out[0].claim
