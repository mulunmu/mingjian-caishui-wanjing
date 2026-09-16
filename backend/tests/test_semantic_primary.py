from __future__ import annotations

import pytest

from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.schemas.semantic_turn import SemanticTurnResult


@pytest.mark.asyncio
async def test_primary_routes_non_analysis_without_composer(monkeypatch):
    from app.services import semantic_primary

    called = False

    async def composer(**kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    out = await semantic_primary.compose_primary_turn(
        db=object(),
        session_id="s1",
        query="你好",
        raw_route={"route": "greeting"},
    )
    assert out.status == "answered"
    assert out.route.route == "greeting"
    assert called is False


@pytest.mark.asyncio
async def test_not_applicable_is_contract_error(monkeypatch):
    from app.services import semantic_primary

    route = ConversationRoute(route="analysis")

    async def composer(**kwargs):
        return SemanticTurnResult(
            status="not_applicable",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
        )

    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)
    with pytest.raises(semantic_primary.PrimaryContractError):
        await semantic_primary.compose_primary_turn(
            db=object(),
            session_id="s1",
            query="分析风险",
            raw_route={"route": "analysis"},
        )
