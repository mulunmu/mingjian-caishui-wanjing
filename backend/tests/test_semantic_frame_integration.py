from __future__ import annotations

import pytest

from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.schemas.semantic_turn import SemanticTurnResult
from app.services.semantic_frame import frame_from_route


def test_route_to_semantic_frame_preserves_policy_and_metrics():
    route = ConversationRoute(route="analysis", domain="loan", entities=["ENT1"])
    frame = frame_from_route(route, query="企业1资产负债率和现金流净额怎么样")
    assert frame.policy_route == "analysis"
    assert frame.task_type == "multi_metric"
    assert {"debt_ratio", "cash_flow_net"}.issubset(set(frame.metrics))


def test_route_to_semantic_frame_tracks_reference_and_language():
    route = ConversationRoute(route="analysis", domain="warn")
    frame = frame_from_route(route, query="回到上上个问题，继续分析")
    assert frame.references
    assert frame.subject_scope == "unbound"


@pytest.mark.asyncio
async def test_primary_response_contains_semantic_frame(monkeypatch):
    from app.services import semantic_primary

    async def composer(**kwargs):
        route = ConversationRoute(route="analysis", domain="loan", entities=["ENT1"])
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply="ok",
        )

    async def persist(**kwargs):
        return None

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)
    out = await semantic_primary.run_primary_turn(
        db=object(),
        session_id="s1",
        owner=None,
        query="资产负债率怎么样",
        raw_route={
            "route": "analysis",
            "domain": "loan",
            "entities": ["ENT1"],
            "needs_tools": True,
            "needs_clarification": False,
        },
    )
    assert out["data"]["primary"]["semantic_frame"]["policy_route"] == "analysis"
