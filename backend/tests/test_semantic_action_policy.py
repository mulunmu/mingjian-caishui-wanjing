from __future__ import annotations

from app.schemas.semantic_action import SemanticAction
from app.services.semantic_policy import resolve_policy


def test_semantic_action_contract_is_small_and_stable():
    assert {item.value for item in SemanticAction} == {
        "analysis",
        "metadata_query",
        "profile",
        "report",
        "conversation",
        "clarify",
        "refuse",
    }


def test_analysis_policy_executes_only_with_permission_and_tool_availability():
    allowed = resolve_policy(
        SemanticAction.ANALYSIS,
        safety="normal",
        permissions={"analysis"},
        tools_available=True,
    )
    denied = resolve_policy(
        SemanticAction.ANALYSIS,
        safety="normal",
        permissions={"analysis"},
        tools_available=False,
    )

    assert allowed.execute_tools is True
    assert allowed.allow_analysis is True
    assert allowed.response_mode == "analysis"
    assert denied.execute_tools is False
    assert denied.allow_analysis is True


def test_report_policy_requires_report_permission_and_confirmation():
    allowed = resolve_policy(
        SemanticAction.REPORT,
        permissions={"report"},
        tools_available=True,
    )
    denied = resolve_policy(
        SemanticAction.REPORT,
        permissions={"analysis"},
        tools_available=True,
    )

    assert allowed.allow_report is True
    assert allowed.requires_confirmation is True
    assert denied.allow_report is False


def test_non_analysis_actions_do_not_execute_tools():
    for action in (
        SemanticAction.METADATA_QUERY,
        SemanticAction.PROFILE,
        SemanticAction.CONVERSATION,
        SemanticAction.CLARIFY,
        SemanticAction.REFUSE,
    ):
        decision = resolve_policy(
            action,
            permissions={"analysis", "report"},
            tools_available=True,
        )
        assert decision.execute_tools is False


def test_safety_block_overrides_every_action():
    decision = resolve_policy(
        SemanticAction.ANALYSIS,
        safety="block",
        permissions={"analysis"},
        tools_available=True,
    )

    assert decision.response_mode == "refuse"
    assert decision.execute_tools is False
    assert decision.allow_analysis is False
    assert decision.allow_report is False


def test_policy_has_no_query_dependency():
    import inspect

    signature = inspect.signature(resolve_policy)
    assert "query" not in signature.parameters
