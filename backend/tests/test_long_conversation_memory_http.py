from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient


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
