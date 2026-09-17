from __future__ import annotations

from app.services.dialog_act import DialogAct
from app.services.shadow_integration import dialog_act_to_raw_route


def test_dialog_act_to_raw_route_maps_analysis_domain():
    raw = dialog_act_to_raw_route(
        DialogAct(act="analyze", scenario="warn", confidence=0.95),
        "企业17交税情况怎么样",
    )
    assert raw["route"] == "analysis"
    assert raw["action"] == "analysis"
    assert raw["domain"] == "warn"
    assert raw["needs_tools"] is True


def test_dialog_act_to_raw_route_maps_greeting():
    raw = dialog_act_to_raw_route(
        DialogAct(act="meta_session", confidence=0.95),
        "你好",
    )
    assert raw["route"] == "greeting"
    assert raw["action"] == "conversation"
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
    assert raw["action"] == "refuse"


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
