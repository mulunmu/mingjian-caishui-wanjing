"""Resolve an action into permissions and execution behavior.

This module deliberately does not accept the user query. Semantic
interpretation belongs to the LLM planner; this layer only answers whether an
already-classified action is allowed to run.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.schemas.semantic_action import (
    SafetyLevel,
    SemanticAction,
    SemanticPolicyDecision,
)


def _permission_set(permissions: Iterable[str] | None) -> frozenset[str]:
    return frozenset(str(item).strip().lower() for item in (permissions or ()) if item)


def resolve_policy(
    action: SemanticAction | str,
    *,
    safety: SafetyLevel = "normal",
    permissions: Iterable[str] | None = None,
    tools_available: bool = False,
) -> SemanticPolicyDecision:
    """Resolve action policy without reading or reclassifying the query."""
    resolved_action = action if isinstance(action, SemanticAction) else SemanticAction(action)
    allowed = _permission_set(permissions)

    if safety == "block":
        return SemanticPolicyDecision(response_mode="refuse")
    if safety == "deescalate":
        return SemanticPolicyDecision(response_mode="deescalate")

    if resolved_action is SemanticAction.ANALYSIS:
        can_analyze = "analysis" in allowed
        return SemanticPolicyDecision(
            response_mode="analysis",
            retrieve_knowledge=can_analyze,
            execute_tools=can_analyze and bool(tools_available),
            allow_analysis=can_analyze,
        )
    if resolved_action is SemanticAction.REPORT:
        can_report = "report" in allowed
        return SemanticPolicyDecision(
            response_mode="report",
            retrieve_knowledge=True,
            allow_report=can_report,
            requires_confirmation=True,
        )
    if resolved_action is SemanticAction.METADATA_QUERY:
        return SemanticPolicyDecision(response_mode="metadata")
    if resolved_action is SemanticAction.PROFILE:
        return SemanticPolicyDecision(response_mode="profile")
    if resolved_action is SemanticAction.CONVERSATION:
        return SemanticPolicyDecision(response_mode="conversation")
    if resolved_action is SemanticAction.CLARIFY:
        return SemanticPolicyDecision(response_mode="clarify")
    return SemanticPolicyDecision(response_mode="refuse")
