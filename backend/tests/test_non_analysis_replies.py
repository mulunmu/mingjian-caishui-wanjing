from __future__ import annotations

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


def test_all_non_analysis_routes_have_formal_reply():
    for route_name in NON_ANALYSIS_ROUTES:
        route = ConversationRoute(route=route_name, domain="general")
        policy = ConversationPolicyRegistry.resolve(route)
        out = build_non_analysis_turn(route, "你好", policy=policy)
        assert out.status in {"answered", "clarify", "abstain"}
        assert out.reply
        assert out.route.route == route_name
        assert out.status != "not_applicable"


def test_product_faq_uses_controlled_knowledge_source():
    route = ConversationRoute(route="product_faq", domain="general")
    policy = ConversationPolicyRegistry.resolve(route)
    out = build_non_analysis_turn(route, "数据怎么导入", policy=policy)
    assert out.status == "answered"
    assert out.meta["faq_id"] == "data"
    assert out.claims
    assert out.reply == out.claims[0].claim
