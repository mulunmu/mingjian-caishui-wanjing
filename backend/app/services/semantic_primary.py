"""Primary semantic dialogue orchestration for all supported route kinds."""
from __future__ import annotations

import os
import re

from app.db.urls import get_sync_engine
from app.schemas.claim import claims_to_dict
from app.schemas.conversation_route import ConversationPolicyRegistry
from app.services.dialog_act import classify as classify_dialog_act
from app.services.non_analysis_replies import build_non_analysis_turn
from app.services.rollout import is_selected, normalize_percent
from app.services.route_normalize import normalize_route
from app.services.semantic_answer_composer import compose_semantic_turn
from app.services.semantic_frame import frame_from_route
from app.services.semantic_turn_persistence import persist_primary_turn
from app.services.shadow_integration import dialog_act_to_raw_route
from app.services.sync_runner import run_blocking
from app.services.topic_memory import resolve_topic_reference_blocking


class PrimaryContractError(RuntimeError):
    """Raised when a primary handler violates the formal-response contract."""


_TOPIC_REFERENCE_RE = re.compile(r"上一个|上上个|上上上|回到.*问题|刚才|之前的")


def primary_enabled() -> bool:
    return os.getenv("SEMANTIC_PRIMARY_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def primary_percent() -> float:
    return normalize_percent(os.getenv("SEMANTIC_PRIMARY_PERCENT", "0"))


def primary_selected(session_id: str, percent: int | float | str | None = None) -> bool:
    return is_selected(session_id, primary_percent() if percent is None else percent)


async def compose_primary_turn(*, db, session_id: str, query: str, raw_route: dict):
    route = normalize_route(raw_route, query)
    policy = ConversationPolicyRegistry.resolve(route)
    may_promote_to_analysis = bool(route.entities) and route.route in {"capability", "clarify"}
    direct_non_analysis = route.route == "language_switch" and not route.entities
    if (
        not direct_non_analysis
        and (policy.execute_tools or route.route in {"analysis", "report"} or may_promote_to_analysis)
    ):
        result = await compose_semantic_turn(
            db=db,
            session_id=session_id,
            query=query,
            raw_route=raw_route,
        )
    else:
        result = build_non_analysis_turn(route, query, policy=policy)

    if result.status == "not_applicable":
        if route.route in {"analysis", "report"}:
            raise PrimaryContractError(f"no primary policy for route={route.route}")
        result = build_non_analysis_turn(route, query, policy=policy)
    result.meta["semantic_frame"] = frame_from_route(route, query=query).model_dump()
    return result


def _primary_meta(turn, *, fallback: bool = False, fallback_reason: str | None = None) -> dict:
    return {
        "status": turn.status,
        "route": turn.route.route,
        "domain": turn.route.domain,
        "fallback": fallback,
        "fallback_reason": fallback_reason,
        "referenced_topic_id": turn.meta.get("referenced_topic_id"),
        "semantic_frame": turn.meta.get("semantic_frame"),
        "candidate_tool_ids": [item.tool_id for item in turn.candidates],
        "plan_tool_ids": [step.tool_id for step in (turn.plan.steps if turn.plan else [])],
    }


def build_primary_chat_response(*, session_id: str, turn) -> dict:
    followups = list(turn.followups)
    function = turn.route.domain or turn.route.route
    if turn.route.route not in {"analysis", "report"}:
        function = "general"
    data = {
        "function": function,
        "dimension": turn.route.domain or "overall",
        "query_type": None,
        "semantic_query": None,
        "industry_l1": None,
        "province": None,
        "enterprise_id": None,
        "claims": claims_to_dict(list(turn.claims)),
        "followups": followups,
        "followup_items": [
            {"type": "query", "label": item, "params": {"query": item}}
            for item in followups
        ],
        "evidence_hidden": True,
        "primary": _primary_meta(turn),
    }
    return {
        "reply": turn.reply or "",
        "reply_source": turn.reply_source or "semantic_primary",
        "analysis_mode": "rule",
        "parse_source": "semantic_primary",
        "intent": turn.route.route,
        "function": function,
        "dimension": turn.route.domain or "overall",
        "session_id": session_id,
        "data": data,
    }


async def run_primary_turn(
    *,
    db,
    session_id: str,
    owner: str | None,
    query: str,
    raw_route: dict | None = None,
    enterprise_id: str | None = None,
) -> dict:
    effective_query = query
    referenced = None
    if _TOPIC_REFERENCE_RE.search(query):
        referenced = await run_blocking(
            resolve_topic_reference_blocking,
            get_sync_engine(),
            session_id,
            query,
        )
    if referenced is not None:
        referenced_intent = referenced.get("intent") or "analysis"
        needs_tools = referenced_intent in {"analysis", "report"}
        raw_route = {
            "route": referenced_intent,
            "domain": referenced.get("scenario"),
            "language": "zh",
            "entities": list(referenced.get("entities") or []),
            "filters": dict(referenced.get("filters") or {}),
            "needs_tools": needs_tools,
            "needs_clarification": referenced_intent == "clarify",
            "confidence": 0.95,
        }
        effective_query = f"{query} {referenced.get('summary') or ''}".strip()
    elif raw_route is None:
        act = await classify_dialog_act(query)
        raw_route = dialog_act_to_raw_route(act, query)
        if (
            enterprise_id
            and getattr(act, "act", None) in {"analyze", "drill"}
            and getattr(act, "refusal_kind", None) is None
        ):
            raw_route = {
                **raw_route,
                "route": "analysis",
                "domain": getattr(act, "scenario", None),
                "needs_tools": True,
                "needs_clarification": False,
            }
    if enterprise_id:
        entities = list(raw_route.get("entities") or [])
        if enterprise_id not in entities:
            entities.insert(0, enterprise_id)
        raw_route = {**raw_route, "entities": entities}
    turn = await compose_primary_turn(
        db=db,
        session_id=session_id,
        query=effective_query,
        raw_route=raw_route,
    )
    if referenced is not None:
        turn.meta["referenced_topic_id"] = referenced["topic_id"]
    await persist_primary_turn(
        db=db,
        session_id=session_id,
        owner=owner,
        query=query,
        turn=turn,
    )
    return build_primary_chat_response(session_id=session_id, turn=turn)
