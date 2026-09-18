from __future__ import annotations

import pytest

from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.services.non_analysis_replies import build_non_analysis_turn


NON_ANALYSIS_ROUTES = [
    "greeting",
    "capability",
    "product_faq",
    "feedback",
    "out_of_domain",
    "abuse",
    "language_switch",
    "unknown_entity",
    "clarify",
    "refuse",
]


async def _fake_policy_reply(*, query, route, facts, status):
    return (f"动态回复:{route}:{query}", "llm")


@pytest.mark.asyncio
async def test_all_non_analysis_routes_use_llm_expression(monkeypatch):
    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "generate_policy_reply", _fake_policy_reply)
    for route_name in NON_ANALYSIS_ROUTES:
        route = ConversationRoute(route=route_name, domain="general")
        policy = ConversationPolicyRegistry.resolve(route)
        out = await build_non_analysis_turn(route, "你好", policy=policy)
        assert out.status in {"answered", "clarify", "abstain"}
        assert out.reply == f"动态回复:{route_name}:你好"
        assert out.reply_source == "llm"
        assert out.route.route == route_name
        assert out.status != "not_applicable"


@pytest.mark.asyncio
async def test_product_faq_keeps_controlled_fact_and_llm_expression(monkeypatch):
    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "generate_policy_reply", _fake_policy_reply)
    route = ConversationRoute(route="product_faq", domain="general")
    policy = ConversationPolicyRegistry.resolve(route)
    out = await build_non_analysis_turn(route, "数据怎么导入", policy=policy)
    assert out.status == "answered"
    assert out.meta["faq_id"] == "data"
    assert out.claims
    assert out.reply_source == "llm"
