"""Read-only shadow path: route -> candidate probe -> policy/candidate correction."""
from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.schemas.conversation_route import (
    ConversationPolicyRegistry,
    ShadowDialogueResult,
)
from app.services.route_normalize import normalize_route
from app.services.tool_rag import ToolRagRetriever, load_tool_snapshot_sync


def build_shadow_dialogue(
    session: Session,
    query: str,
    raw_route: dict,
) -> ShadowDialogueResult:
    route = normalize_route(raw_route, query)
    policy = ConversationPolicyRegistry.resolve(route)
    probe_allowed = (
        policy.retrieve_candidates
        or bool(route.entities)
        or route.route in {"analysis", "report", "clarify", "capability"}
    )
    candidates = []
    if probe_allowed:
        bind = session.get_bind()
        if not isinstance(bind, Engine):
            raise RuntimeError("shadow dialogue requires an Engine-bound session")
        snapshot = load_tool_snapshot_sync(bind)
        candidates = ToolRagRetriever(snapshot).retrieve(
            query,
            domain=route.domain,
            top_k=10,
        )

    if (
        route.route in {"capability", "clarify"}
        and route.entities
        and candidates
    ):
        route = route.model_copy(
            update={
                "route": "analysis",
                "needs_tools": True,
                "needs_clarification": False,
                "confidence": max(float(route.confidence or 0.0), 0.8),
            }
        )
        policy = ConversationPolicyRegistry.resolve(route)

    return ShadowDialogueResult(route=route, policy=policy, candidates=candidates)