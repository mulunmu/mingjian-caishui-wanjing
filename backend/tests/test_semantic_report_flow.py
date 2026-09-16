from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.route_normalize import normalize_route
from app.services.semantic_report_flow import (
    build_custom_report_turn,
    build_fixed_report_turn,
)
from app.schemas.conversation_route import ConversationPolicyRegistry
from app.schemas.semantic_turn import SemanticTurnResult


def _report_route():
    return normalize_route(
        {
            "route": "report",
            "domain": "report",
            "language": "zh",
            "entities": [],
            "needs_tools": False,
            "needs_clarification": False,
            "confidence": 0.95,
        },
        "生成评级报告",
    )


@pytest.mark.asyncio
async def test_fixed_report_generates_slice_and_exposes_download(monkeypatch):
    from app.services import slice_report

    async def generate(*_args, **_kwargs):
        return "slice_report_1", None, {"title": "评级风险报告"}

    monkeypatch.setattr(slice_report, "generate_slice_report", generate)
    turn = await build_fixed_report_turn(
        db=object(),
        session_id="s1",
        owner="user@example.com",
        user={"sub": "user@example.com", "role": "user", "plan": "subscriber"},
        query="生成评级报告",
        route=_report_route(),
    )

    assert turn.status == "answered"
    assert turn.meta["report"]["report_id"] == "slice_report_1"
    assert turn.meta["report"]["download_url"].endswith("/slice_report_1/download")
    assert turn.claims[0].value.metric == "report"
    assert "slice_report_1" in (turn.reply or "")


@pytest.mark.asyncio
async def test_fixed_report_generates_enterprise_report_when_subject_is_bound(monkeypatch):
    from app.services import slice_report

    async def generate(*_args, **_kwargs):
        return "ent_report_1", None, {"title": "企业深度报告"}

    monkeypatch.setattr(slice_report, "generate_enterprise_report", generate)
    turn = await build_fixed_report_turn(
        db=object(),
        session_id="s1",
        owner="user@example.com",
        user={"sub": "user@example.com", "role": "user", "plan": "subscriber"},
        query="生成企业报告",
        route=_report_route(),
        enterprise_id="ENT001",
    )

    assert turn.meta["report"]["kind"] == "enterprise"
    assert turn.meta["report"]["report_id"] == "ent_report_1"


@pytest.mark.asyncio
async def test_fixed_report_is_subscription_gated_before_generation(monkeypatch):
    from app.services import slice_report

    generate = AsyncMock()
    monkeypatch.setattr(slice_report, "generate_slice_report", generate)
    turn = await build_fixed_report_turn(
        db=object(),
        session_id="s1",
        owner=None,
        user=None,
        query="生成评级报告",
        route=_report_route(),
    )

    generate.assert_not_awaited()
    assert turn.meta["report_locked"] is True
    assert turn.claims[0].value.metric == "subscription_required"


@pytest.mark.asyncio
async def test_custom_report_confirmation_generates_and_keeps_state(monkeypatch):
    from app.services import assessment, custom_report, slice_report

    monkeypatch.setattr(
        assessment,
        "resolve_enterprise_ids",
        AsyncMock(return_value=["e1"]),
    )

    async def generate_custom(*_args, **_kwargs):
        return "custom_report_1", None, {"title": "定制风险报告"}

    monkeypatch.setattr(slice_report, "generate_custom_report", generate_custom)
    state = custom_report.new_state()
    state.update(
        {
            "active": True,
            "stage": "propose",
            "spec": {
                "chapters": ["financial", "tax"],
                "industry_l1": "制造",
                "province": None,
                "enterprises": ["企业1"],
                "title": "定制风险报告",
                "tone": None,
                "purpose": "财务税务",
            },
        }
    )
    turn = await build_custom_report_turn(
        db=object(),
        session_id="s1",
        owner="user@example.com",
        user={"sub": "user@example.com", "role": "user", "plan": "subscriber"},
        query="确认生成",
        route=_report_route(),
        state=state,
    )

    assert turn.meta["report"]["report_id"] == "custom_report_1"
    assert turn.meta["custom_report_state"]["active"] is False
    assert turn.claims[0].value.metric == "report"


@pytest.mark.asyncio
async def test_custom_report_asking_advances_state_machine(monkeypatch):
    from app.services import custom_report

    async def next_turn(state, answer):
        state["stage"] = "asking"
        return {
            "reply": "请告诉我报告想解决什么风险。",
            "followups": ["退出定制"],
            "stage": "asking",
            "spec": None,
            "meta": {},
            "llm": False,
        }

    monkeypatch.setattr(custom_report, "next_turn", next_turn)
    turn = await build_custom_report_turn(
        db=object(),
        session_id="s1",
        owner="user@example.com",
        user={"sub": "user@example.com", "role": "user", "plan": "subscriber"},
        query="我要定制报告",
        route=_report_route(),
        state=None,
    )

    assert turn.status == "clarify"
    assert turn.meta["custom_report_state"]["stage"] == "asking"
    assert turn.reply == "请告诉我报告想解决什么风险。"


@pytest.mark.asyncio
async def test_primary_report_route_dispatches_to_active_report_flow(monkeypatch):
    from app.services import semantic_primary, session_store

    route = _report_route()
    flow_turn = SemanticTurnResult(
        status="answered",
        route=route,
        policy=ConversationPolicyRegistry.resolve(route),
        reply="报告已生成",
        meta={"report": {"report_id": "r1"}},
    )
    dispatch = AsyncMock(return_value=flow_turn)
    persist = AsyncMock()
    monkeypatch.setattr(session_store, "get_session", lambda _sid: None)
    monkeypatch.setattr(semantic_primary, "build_fixed_report_turn", dispatch)
    monkeypatch.setattr(semantic_primary, "persist_primary_turn", persist)

    out = await semantic_primary.run_primary_turn(
        db=object(),
        session_id="s1",
        owner="user@example.com",
        user={"sub": "user@example.com", "role": "user", "plan": "subscriber"},
        query="生成评级报告",
        raw_route={"route": "report", "domain": "report", "needs_tools": False},
    )

    dispatch.assert_awaited_once()
    persist.assert_awaited_once()
    assert out["reply"] == "报告已生成"
    assert out["data"]["report"]["report_id"] == "r1"
