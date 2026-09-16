from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.shadow_answer_evaluation import ShadowAnswerObservationRecord
from app.schemas.conversation_route import ConversationPolicyRegistry
from app.schemas.semantic_turn import SemanticTurnResult
from app.services.route_normalize import normalize_route
from app.services.shadow_answer_evaluation import (
    build_shadow_answer_summary,
    evaluate_shadow_answer,
    save_shadow_answer_observation,
)
from tests.test_semantic_registry_seed import _engine


def _answer_engine():
    engine = _engine()
    Base.metadata.create_all(engine, tables=[ShadowAnswerObservationRecord.__table__])
    return engine


def _turn(status: str = "answered") -> SemanticTurnResult:
    route = normalize_route(
        {
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": ["ENT017"],
            "needs_tools": True,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        "企业17资产负债率高不高",
    )
    policy = ConversationPolicyRegistry.resolve(route)
    return SemanticTurnResult(
        status=status,
        route=route,
        policy=policy,
        reply="ok" if status == "answered" else None,
        followups=[],
    )


@pytest.mark.asyncio
async def test_evaluate_shadow_answer_records_answered_observation(monkeypatch):
    from app.services import shadow_answer_evaluation

    monkeypatch.setattr(
        shadow_answer_evaluation,
        "compose_semantic_turn",
        AsyncMock(return_value=_turn("answered")),
    )
    observation = await evaluate_shadow_answer(
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
        },
    )
    assert observation.status == "answered"
    assert observation.reply_present is True
    assert observation.claim_count == 0


@pytest.mark.asyncio
async def test_evaluate_shadow_answer_records_error(monkeypatch):
    from app.services import shadow_answer_evaluation

    monkeypatch.setattr(
        shadow_answer_evaluation,
        "compose_semantic_turn",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    observation = await evaluate_shadow_answer(
        db=object(),
        session_id="session-1",
        query="企业17资产负债率高不高",
        raw_route={"route": "analysis", "domain": "warn"},
    )
    assert observation.status == "error"
    assert "boom" in (observation.error or "")


def test_save_and_summarize_shadow_answers():
    engine = _answer_engine()
    observation = None
    for index in range(20):
        import asyncio

        observation = asyncio.run(
            evaluate_shadow_answer(
                db=object(),
                session_id=f"session-{index}",
                query=f"query-{index}",
                raw_route={"route": "analysis", "domain": "warn"},
                composer=AsyncMock(return_value=_turn("answered")),
            )
        )
        save_shadow_answer_observation(engine, observation)
    summary = build_shadow_answer_summary(engine, min_samples=20)
    assert summary["ok"] is True
    assert summary["samples"] == 20
    assert summary["answer_rate"] == 1.0