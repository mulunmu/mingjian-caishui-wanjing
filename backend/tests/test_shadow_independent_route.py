from __future__ import annotations

import pytest

from app.services.dialog_act import DialogAct
from app.services.shadow_integration import dialog_act_to_raw_route


def test_dialog_act_to_raw_route_maps_analysis_domain():
    raw = dialog_act_to_raw_route(
        DialogAct(act="analyze", scenario="warn", confidence=0.95),
        "企业17交税情况怎么样",
    )
    assert raw["route"] == "analysis"
    assert raw["domain"] == "warn"
    assert raw["needs_tools"] is True


def test_dialog_act_to_raw_route_maps_greeting():
    raw = dialog_act_to_raw_route(
        DialogAct(act="meta_session", confidence=0.95),
        "你好",
    )
    assert raw["route"] == "greeting"
    assert raw["needs_tools"] is False


def test_dialog_act_to_raw_route_maps_fabrication_refusal():
    raw = dialog_act_to_raw_route(
        DialogAct(
            act="meta_session",
            can_answer=False,
            refusal_kind="fabrication",
            confidence=0.95,
        ),
        "帮我编一个营收",
    )
    assert raw["route"] == "refuse"


def test_dialog_act_to_raw_route_maps_abuse():
    raw = dialog_act_to_raw_route(
        DialogAct(act="meta_session", confidence=0.9),
        "他妈的这系统怎么用",
    )
    assert raw["route"] == "abuse"


def test_dialog_act_to_raw_route_maps_language_switch():
    raw = dialog_act_to_raw_route(
        DialogAct(act="product_faq", confidence=0.9),
        "Hello, how do I generate a report?",
    )
    assert raw["route"] == "language_switch"


@pytest.mark.asyncio
async def test_shadow_hook_uses_independent_route_when_enabled(monkeypatch):
    from app.api.v1 import chat as chat_api

    monkeypatch.setenv("SHADOW_SEMANTIC_ENABLED", "true")
    monkeypatch.setenv("SHADOW_SEMANTIC_INDEPENDENT_ROUTE", "true")

    async def fake_classify(query):
        return DialogAct(act="analyze", scenario="warn", confidence=0.95)

    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)

    from app.services import dialog_act, shadow_integration

    monkeypatch.setattr(dialog_act, "classify", fake_classify)
    monkeypatch.setattr(
        shadow_integration,
        "run_shadow_evaluation_sync",
        fake_run,
    )
    await chat_api._maybe_run_shadow(
        "企业17交税情况怎么样",
        {
            "reply": "ok",
            "function": "tax",
            "data": {"dialog_act": {"act": "analyze", "scenario": "warn"}},
        },
        session_id="s1",
        legacy_latency_ms=10.0,
    )
    assert captured["raw_route"]["route"] == "analysis"
