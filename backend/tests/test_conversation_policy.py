from __future__ import annotations

from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute


def _route(route: str, **updates) -> ConversationRoute:
    payload = {
        "route": route,
        "language": "zh",
        "safety": "normal",
        "entities": [],
        "needs_tools": False,
        "needs_clarification": False,
        "confidence": 0.95,
    }
    payload.update(updates)
    return ConversationRoute(**payload)


def test_greeting_has_no_retrieval_or_execution():
    policy = ConversationPolicyRegistry.resolve(_route("greeting"))
    assert policy.retrieve_candidates is False
    assert policy.execute_tools is False


def test_capability_uses_capability_namespace():
    policy = ConversationPolicyRegistry.resolve(_route("capability"))
    assert policy.knowledge_namespace == "capability"
    assert policy.execute_tools is False


def test_clarification_can_retrieve_candidates_but_not_execute():
    policy = ConversationPolicyRegistry.resolve(
        _route("analysis", needs_tools=True, needs_clarification=True)
    )
    assert policy.response_mode == "clarify"
    assert policy.retrieve_candidates is True
    assert policy.execute_tools is False


def test_analysis_executes_after_valid_plan():
    policy = ConversationPolicyRegistry.resolve(
        _route("analysis", needs_tools=True)
    )
    assert policy.retrieve_candidates is True
    assert policy.execute_tools is True


def test_abuse_safety_overrides_analysis():
    policy = ConversationPolicyRegistry.resolve(
        _route("analysis", needs_tools=True, safety="deescalate")
    )
    assert policy.response_mode == "deescalate"
    assert policy.retrieve_candidates is False
    assert policy.execute_tools is False
