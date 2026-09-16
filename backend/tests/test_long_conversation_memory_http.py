from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_http_topic_reference_survives_ten_intervening_turns(live_db):
    del live_db
    from app.main import app

    session_id = f"stage14c-{uuid.uuid4().hex}"
    with TestClient(app) as client:
        for index in range(1, 13):
            response = client.post(
                "/api/v1/chat",
                json={
                    "query": f"你好，介绍一下系统能力 {index}",
                    "session_id": session_id,
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["data"]["primary"]["fallback"] is False

        response = client.post(
            "/api/v1/chat",
            json={
                "query": "回到第10个问题继续分析",
                "session_id": session_id,
            },
        )

    assert response.status_code == 200, response.text
    primary = response.json()["data"]["primary"]
    assert primary["fallback"] is False
    assert primary["referenced_topic_id"].endswith("-topic-10")


@pytest.mark.asyncio
async def test_http_multi_intent_persists_one_combined_topic(monkeypatch, live_db):
    del live_db
    from app.db.urls import get_sync_engine
    from app.main import app
    from app.models.semantic_registry import ConversationTopic
    from app.schemas.claim import Claim, ClaimTrace, ClaimValue
    from app.schemas.conversation_route import (
        ConversationPolicyRegistry,
        ConversationRoute,
    )
    from app.services import semantic_primary
    from app.services.dialog_act import DialogAct

    async def classify(query, context):
        del query, context
        return DialogAct(
            act="analyze",
            scenario="warn",
            scope_target="individual",
            confidence=0.95,
        )

    async def composer(**kwargs):
        query = kwargs["query"]
        if "资产负债率" in query:
            metric, number, query_id = "debt_ratio", 0.8, "Q-http-debt"
        else:
            metric, number, query_id = "cash_flow_net", -10.0, "Q-http-cash"
        route = ConversationRoute(
            route="analysis",
            domain="warn",
            entities=["ENT1"],
        )
        return semantic_primary.SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            claims=[
                Claim(
                    claim=f"{metric} claim",
                    value=ClaimValue(metric=metric, number=number, unit=""),
                    trace=ClaimTrace(
                        table="core_metrics",
                        field=metric,
                        query_id=query_id,
                    ),
                    confidence="computed",
                )
            ],
            reply=f"{metric} reply",
        )

    monkeypatch.setattr(semantic_primary, "classify_dialog_act", classify)
    monkeypatch.setattr(semantic_primary, "compose_semantic_turn", composer)

    session_id = f"stage14e-{uuid.uuid4().hex}"
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "query": "分析ENT1的资产负债率；分析ENT1的现金流",
                "session_id": session_id,
                "enterprise_id": "ENT1",
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["data"]["primary"]["multi_intent"] is True
    assert len(data["data"]["claims"]) == 2
    with Session(get_sync_engine()) as session:
        count = session.scalar(
            select(func.count()).select_from(ConversationTopic).where(
                ConversationTopic.session_id == session_id
            )
        )
    assert count == 1
