"""Primary semantic dialogue orchestration for all supported route kinds."""
from __future__ import annotations

from app.schemas.conversation_route import ConversationPolicyRegistry
from app.services.non_analysis_replies import build_non_analysis_turn
from app.services.route_normalize import normalize_route
from app.services.semantic_answer_composer import compose_semantic_turn


class PrimaryContractError(RuntimeError):
    """Raised when a primary handler violates the formal-response contract."""


async def compose_primary_turn(*, db, session_id: str, query: str, raw_route: dict):
    route = normalize_route(raw_route, query)
    policy = ConversationPolicyRegistry.resolve(route)
    if policy.execute_tools or route.route in {"analysis", "report"}:
        result = await compose_semantic_turn(
            db=db,
            session_id=session_id,
            query=query,
            raw_route=raw_route,
        )
    else:
        result = build_non_analysis_turn(route, query, policy=policy)

    if result.status == "not_applicable":
        raise PrimaryContractError(f"no primary policy for route={route.route}")
    return result
