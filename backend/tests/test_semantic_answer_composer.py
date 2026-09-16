from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.semantic_answer_composer import compose_semantic_turn, resolve_enterprise_entities
from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.tool_rag import load_tool_snapshot_sync
from tests.test_semantic_registry_seed import _engine


def _snapshot():
    engine = _engine()
    seed_semantic_registry(engine)
    return load_tool_snapshot_sync(engine)


@pytest.mark.asyncio
async def test_semantic_composer_runs_executable_plan_and_returns_guarded_reply(monkeypatch):
    async def fake_run_semantic_query(db, sq, session_id):
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

    async def fake_reply(query, claims, followups, **kwargs):
        return (
            "资产负债率 72.00，偿债压力需要结合现金流判断。",
            MagicMock(followups=[]),
            "llm",
        )

    from app.services import judgment_service, llm_reply

    monkeypatch.setattr(judgment_service, "run_semantic_query", fake_run_semantic_query)
    monkeypatch.setattr(llm_reply, "generate_claim_reply", fake_reply)

    out = await compose_semantic_turn(
        db=object(),
        session_id="session-1",
        query="企业17资产负债率高不高",
        raw_route={
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": ["ENT017"],
            "needs_tools": True,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        snapshot=_snapshot(),
    )
    assert out.status == "answered"
    assert out.plan is not None
    assert out.plan.steps[0].tool_id == "metric_debt_ratio"
    assert out.claims[0].value.metric == "debt_ratio"
    assert "72.00" in (out.reply or "")
    assert "999" not in (out.reply or "")


@pytest.mark.asyncio
async def test_semantic_composer_clarifies_when_route_requires_clarification():
    out = await compose_semantic_turn(
        db=object(),
        session_id="session-1",
        query="公司稳不稳",
        raw_route={
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": True,
            "confidence": 0.5,
        },
        snapshot=_snapshot(),
    )
    assert out.status == "clarify"
    assert out.plan is None
    assert out.reply


@pytest.mark.asyncio
async def test_semantic_composer_abstains_without_executable_candidates():
    out = await compose_semantic_turn(
        db=object(),
        session_id="session-1",
        query="完全无法识别的问题",
        raw_route={
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": ["ENT017"],
            "needs_tools": True,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        snapshot=_snapshot(),
    )
    assert out.status == "abstain"
    assert out.plan is None


@pytest.mark.asyncio
async def test_semantic_composer_does_not_apply_to_greeting():
    out = await compose_semantic_turn(
        db=object(),
        session_id="session-1",
        query="你好",
        raw_route={
            "route": "greeting",
            "language": "zh",
            "entities": [],
            "needs_tools": False,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        snapshot=_snapshot(),
    )
    assert out.status == "not_applicable"
    assert out.plan is None

@pytest.mark.asyncio
async def test_resolve_enterprise_display_name(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "ENT017"
    db.execute.return_value = result
    resolved = await resolve_enterprise_entities(db, ["企业17"])
    assert resolved == ["ENT017"]


@pytest.mark.asyncio
async def test_semantic_composer_clarifies_unresolved_entity():
    from unittest.mock import AsyncMock, MagicMock

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    out = await compose_semantic_turn(
        db=db,
        session_id="session-1",
        query="不存在企业资产负债率高不高",
        raw_route={
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": ["不存在企业"],
            "needs_tools": True,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        snapshot=_snapshot(),
    )
    assert out.status == "clarify"
    assert out.plan is None

@pytest.mark.asyncio
async def test_composer_promotes_weak_route_when_candidate_exists(monkeypatch):
    async def fake_run_semantic_query(db, sq, session_id):
        return (
            [
                Claim(
                    claim="样本红字发票数量 3 张。",
                    value=ClaimValue(metric="red_invoice_cnt", number=3, unit="张"),
                    trace=ClaimTrace(
                        table="core_metrics",
                        field="red_invoice_cnt",
                        query_id="Q_test",
                    ),
                    confidence="computed",
                )
            ],
            [],
            {"function": "fraud", "dimension": "overall", "query_type": "lookup"},
        )

    async def fake_reply(query, claims, followups, **kwargs):
        return ("红字发票数量为 3 张。", MagicMock(followups=[]), "llm")

    from app.services import judgment_service, llm_reply

    monkeypatch.setattr(judgment_service, "run_semantic_query", fake_run_semantic_query)
    monkeypatch.setattr(llm_reply, "generate_claim_reply", fake_reply)

    out = await compose_semantic_turn(
        db=object(),
        session_id="session-1",
        query="企业2红字发票有多少",
        raw_route={
            "route": "capability",
            "domain": "general",
            "language": "zh",
            "entities": ["ENT002"],
            "needs_tools": False,
            "needs_clarification": False,
            "confidence": 0.4,
        },
        snapshot=_snapshot(),
    )
    assert out.status == "answered"
    assert out.plan is not None
    assert out.plan.steps[0].tool_id == "metric_red_invoice_cnt"