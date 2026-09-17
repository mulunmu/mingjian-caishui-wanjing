"""Primary semantic dialogue orchestration for all supported route kinds."""
from __future__ import annotations

import logging
import os
import re

from app.db.urls import get_sync_engine
from app.db.session import get_async_session_factory
from app.schemas.claim import Claim, claims_to_dict
from app.schemas.conversation_route import (
    ConversationPolicyRegistry,
    ConversationRoute,
)
from app.schemas.semantic_turn import SemanticTurnResult
from app.services.dialog_act import (
    classify as classify_dialog_act,
    split_multi_intent,
)
from app.services.dialogue_composition import build_dialogue_composition_plan
from app.services.non_analysis_replies import build_non_analysis_turn
from app.services.observability import get_trace_id
from app.services.rollout import is_selected, normalize_percent
from app.services.route_normalize import normalize_route
from app.services.composition_execution_bridge import execute_metric_composition
from app.services.semantic_answer_composer import compose_semantic_turn
from app.services.semantic_frame import frame_from_route
from app.services.semantic_report_flow import (
    build_custom_report_turn,
    build_fixed_report_turn,
)
from app.services.semantic_turn_persistence import persist_primary_turn
from app.services import session_store
from app.services.shadow_integration import dialog_act_to_raw_route
from app.services.sync_runner import run_blocking
from app.services.topic_memory import (
    compose_memory_context_blocking,
    looks_like_topic_reference,
    resolve_topic_reference_blocking,
)
from app.services.tool_rag import load_tool_snapshot


logger = logging.getLogger(__name__)


class PrimaryContractError(RuntimeError):
    """Raised when a primary handler violates the formal-response contract."""


def promote_route_with_frame(route, frame):
    if (
        len(frame.metrics) >= 2
        and frame.entities
        and route.route in {"clarify", "capability"}
    ):
        return route.model_copy(
            update={
                "route": "analysis",
                "domain": route.domain or "warn",
                "needs_tools": True,
                "needs_clarification": False,
                "confidence": max(float(route.confidence or 0.0), 0.85),
            }
        )
    return route


_TOPIC_REFERENCE_RE = re.compile(
    r"上一个|上上个|上上上|回到.*问题|刚才|之前的|"
    r"第\s*[0-9一二三四五六七八九十两]+\s*(?:个)?(?:问题|轮|话题)|"
    r"往前(?:数|回)?\s*[0-9一二三四五六七八九十两]+|"
    r"[0-9一二三四五六七八九十两]+\s*(?:轮|个问题).*?(?:之前|以前)"
)


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
        "trace_id": get_trace_id(),
        "topic_match_score": turn.meta.get("topic_match_score"),
        "topic_match_reason": turn.meta.get("topic_match_reason"),
        "semantic_frame": turn.meta.get("semantic_frame"),
        "composition_plan_id": turn.meta.get("composition_plan_id"),
        "composition_elapsed_ms": turn.meta.get("composition_elapsed_ms"),
        "composition_completed_order": turn.meta.get("composition_completed_order"),
        "composition_cache_hits": turn.meta.get("composition_cache_hits") or [],
        "composition_failed_nodes": turn.meta.get("composition_failed_nodes") or [],
        "composition_skipped_nodes": turn.meta.get("composition_skipped_nodes") or [],
        "composition_total_cost": turn.meta.get("composition_total_cost"),
        "composition_registry_version": turn.meta.get("composition_registry_version"),
        "composition_blueprint_persisted": turn.meta.get(
            "composition_blueprint_persisted"
        ),
        "composition_execution_id": turn.meta.get("composition_execution_id"),
        "candidate_tool_ids": [item.tool_id for item in turn.candidates],
        "plan_tool_ids": [step.tool_id for step in (turn.plan.steps if turn.plan else [])],
        "dialogue_composition_plan_id": turn.meta.get(
            "dialogue_composition_plan_id"
        ),
        "dialogue_intent_modules": turn.meta.get("dialogue_intent_modules") or [],
        "dialogue_policy_modules": turn.meta.get("dialogue_policy_modules") or [],
        "dialogue_content_modules": turn.meta.get("dialogue_content_modules") or [],
        "multi_intent": bool(turn.meta.get("multi_intent")),
        "multi_intent_segments": turn.meta.get("multi_intent_segments") or [],
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
        "report": turn.meta.get("report"),
        "report_id": turn.meta.get("report_id"),
        "report_hint": turn.meta.get("report_hint"),
        "report_locked": bool(turn.meta.get("report_locked")),
        "actions": list(turn.meta.get("actions") or []),
        "cards": list(turn.meta.get("cards") or []),
        "custom_report": turn.meta.get("custom_report_state"),
        "custom_report_proposal": turn.meta.get("custom_report_proposal"),
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
        "trace_id": get_trace_id(),
        "data": data,
    }


_ROUTE_PRIORITY = {
    "report": 100,
    "analysis": 90,
    "language_switch": 80,
    "capability": 70,
    "product_faq": 65,
    "clarify": 60,
    "unknown_entity": 55,
    "refuse": 50,
    "out_of_domain": 45,
    "feedback": 40,
    "abuse": 30,
    "greeting": 20,
}


def _response_route(response: dict) -> ConversationRoute:
    route_kind = str(response.get("intent") or "clarify")
    if route_kind not in _ROUTE_PRIORITY:
        route_kind = "clarify"
    domain = response.get("dimension")
    if domain not in {"loan", "rating", "warn", "audit", "report", "general"}:
        domain = None
    return ConversationRoute(route=route_kind, domain=domain)


def _claim_from_response(response: dict) -> list[Claim]:
    claims: list[Claim] = []
    for item in (response.get("data") or {}).get("claims") or []:
        try:
            claims.append(Claim.model_validate(item))
        except Exception:
            continue
    return claims


async def _run_multi_intent_turn(
    *,
    db,
    session_id: str,
    owner: str | None,
    query: str,
    enterprise_id: str | None,
    user: dict | None,
    segments: list[str],
) -> dict:
    responses: list[dict] = []
    for segment in segments:
        responses.append(
            await run_primary_turn(
                db=db,
                session_id=session_id,
                owner=owner,
                query=segment,
                enterprise_id=enterprise_id,
                user=user,
                persist=False,
            )
        )

    selected = max(
        responses,
        key=lambda item: _ROUTE_PRIORITY.get(str(item.get("intent")), 0),
    )
    route = _response_route(selected)
    policy = ConversationPolicyRegistry.resolve(route)
    claims: list[Claim] = []
    seen_claims: set[str] = set()
    followups: list[str] = []
    actions: list[dict] = []
    cards: list[dict] = []
    report_ids: list[str] = []
    result_rows: list[dict] = []
    for segment, response in zip(segments, responses, strict=True):
        for claim in _claim_from_response(response):
            key = claim.model_dump_json()
            if key not in seen_claims:
                seen_claims.add(key)
                claims.append(claim)
        for item in response.get("followups") or []:
            if isinstance(item, str) and item not in followups:
                followups.append(item)
        data = response.get("data") or {}
        for item in data.get("actions") or []:
            if isinstance(item, dict) and item not in actions:
                actions.append(item)
        for item in data.get("cards") or []:
            if isinstance(item, dict) and item not in cards:
                cards.append(item)
        report_id = data.get("report_id")
        if report_id and report_id not in report_ids:
            report_ids.append(str(report_id))
        result_rows.append(
            {
                "segment": segment,
                "intent": response.get("intent"),
                "reply": response.get("reply"),
                "claim_count": len(_claim_from_response(response)),
                "report_id": report_id,
            }
        )

    plan = build_dialogue_composition_plan(
        query=query,
        segments=segments,
        intent_hints=[str(item.get("intent") or "") for item in responses],
    )
    if plan is None:
        raise PrimaryContractError("multi-intent dialogue composition validation failed")
    reply = "\n\n".join(
        f"【{segment}】\n{str(response.get('reply') or '').strip()}"
        for segment, response in zip(segments, responses, strict=True)
    ).strip()
    turn = SemanticTurnResult(
        status="answered",
        route=route,
        policy=policy,
        claims=claims,
        reply=reply,
        followups=followups[:8],
        reply_source="multi_intent",
        meta={
            "dialogue_composition_plan": plan.model_dump(),
            "dialogue_composition_plan_id": plan.plan_id,
            "dialogue_intent_modules": plan.metadata.get("intent_module_ids"),
            "dialogue_policy_modules": plan.metadata.get("policy_module_ids"),
            "dialogue_content_modules": plan.metadata.get("content_module_ids"),
            "multi_intent": True,
            "multi_intent_segments": segments,
            "multi_intent_results": result_rows,
            "report_ids": report_ids,
            "actions": actions,
            "cards": cards,
        },
    )
    turn.meta["semantic_frame"] = frame_from_route(route, query=query).model_dump()
    await persist_primary_turn(
        db=db,
        session_id=session_id,
        owner=owner,
        query=query,
        turn=turn,
    )
    return build_primary_chat_response(session_id=session_id, turn=turn)


async def run_primary_turn(
    *,
    db,
    session_id: str,
    owner: str | None,
    query: str,
    raw_route: dict | None = None,
    enterprise_id: str | None = None,
    user: dict | None = None,
    persist: bool = True,
    memory_context: dict | None = None,
) -> dict:
    segments = split_multi_intent(query)
    if persist and len(segments) >= 2:
        return await _run_multi_intent_turn(
            db=db,
            session_id=session_id,
            owner=owner,
            query=query,
            enterprise_id=enterprise_id,
            user=user,
            segments=segments,
        )
    effective_query = query
    referenced = None
    has_topic_reference = looks_like_topic_reference(query)
    session_context = await run_blocking(session_store.get_session, session_id)
    memory_context = memory_context or {}
    if has_topic_reference:
        if not memory_context:
            try:
                memory_context = await run_blocking(
                    compose_memory_context_blocking,
                    get_sync_engine(),
                    session_id,
                    query=query,
                )
            except Exception as exc:
                logger.warning(
                    "semantic memory context unavailable for session %s: %s",
                    session_id,
                    exc,
                )
    custom_state = (
        (session_context or {}).get("custom_report")
        if isinstance(session_context, dict)
        else None
    )
    custom_act = False
    if has_topic_reference and memory_context.get("referenced_topic_id"):
        referenced = {
            "topic_id": memory_context["referenced_topic_id"],
            "summary": memory_context.get("referenced_summary"),
            "entities": memory_context.get("referenced_entities") or [],
            "filters": memory_context.get("referenced_filters") or {},
            "scenario": memory_context.get("referenced_scenario"),
            "intent": memory_context.get("referenced_intent") or "analysis",
            "tool_plan": memory_context.get("referenced_tool_plan") or [],
            "claim_ids": memory_context.get("referenced_claim_ids") or [],
            "report_ids": memory_context.get("referenced_report_ids") or [],
            "match_score": memory_context.get("topic_match_score"),
            "match_reason": memory_context.get("topic_match_reason"),
        }
    elif has_topic_reference:
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
    elif has_topic_reference and memory_context.get("session_summary"):
        effective_query = f"{query} 历史摘要：{memory_context['session_summary']}"
    elif raw_route is None:
        act = await classify_dialog_act(query, session_context or {})
        custom_act = getattr(act, "act", None) == "custom_report"
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
    route = normalize_route(raw_route, effective_query)
    policy = ConversationPolicyRegistry.resolve(route)
    frame = frame_from_route(route, query=effective_query)
    dialogue_plan = build_dialogue_composition_plan(
        query=query,
        frame=frame,
    )
    if dialogue_plan is None:
        raise PrimaryContractError("dialogue composition validation failed")
    promoted_route = promote_route_with_frame(route, frame)
    if promoted_route.route != route.route:
        route = promoted_route
        policy = ConversationPolicyRegistry.resolve(route)
        frame = frame_from_route(route, query=effective_query)
    turn = None
    custom_active = bool(
        isinstance(custom_state, dict) and custom_state.get("active")
    )
    if route.route == "report" or custom_act or custom_active:
        report_route = route
        if report_route.route != "report":
            report_route = normalize_route(
                {
                    "route": "report",
                    "domain": "report",
                    "language": "zh",
                    "entities": list(raw_route.get("entities") or []),
                    "needs_tools": False,
                    "needs_clarification": False,
                    "confidence": 0.95,
                },
                effective_query,
            )
        if custom_act or custom_active:
            turn = await build_custom_report_turn(
                db=db,
                session_id=session_id,
                owner=owner,
                user=user,
                query=effective_query,
                route=report_route,
                state=custom_state,
            )
        else:
            turn = await build_fixed_report_turn(
                db=db,
                session_id=session_id,
                owner=owner,
                user=user,
                query=effective_query,
                route=report_route,
                enterprise_id=enterprise_id,
                raw_entities=list(raw_route.get("entities") or []),
            )
    if route.route == "analysis" and len(frame.metrics) >= 2:
        try:
            snapshot = await load_tool_snapshot(db)
            turn = await execute_metric_composition(
                frame=frame,
                route=route,
                policy=policy,
                query=effective_query,
                session_id=session_id,
                owner=owner,
                snapshot=snapshot,
                session_factory=get_async_session_factory(),
            )
        except Exception:
            turn = None
    if turn is None:
        turn = await compose_primary_turn(
            db=db,
            session_id=session_id,
            query=effective_query,
            raw_route=raw_route,
        )
    turn.meta["semantic_frame"] = frame.model_dump()
    turn.meta["dialogue_composition_plan"] = dialogue_plan.model_dump()
    turn.meta["dialogue_composition_plan_id"] = dialogue_plan.plan_id
    turn.meta["dialogue_intent_modules"] = dialogue_plan.metadata.get(
        "intent_module_ids"
    )
    turn.meta["dialogue_policy_modules"] = dialogue_plan.metadata.get(
        "policy_module_ids"
    )
    turn.meta["dialogue_content_modules"] = dialogue_plan.metadata.get(
        "content_module_ids"
    )
    if referenced is not None:
        turn.meta["referenced_topic_id"] = referenced["topic_id"]
        turn.meta["topic_match_score"] = referenced.get("match_score")
        turn.meta["topic_match_reason"] = referenced.get("match_reason")
    if persist:
        await persist_primary_turn(
            db=db,
            session_id=session_id,
            owner=owner,
            query=query,
            turn=turn,
        )
    return build_primary_chat_response(session_id=session_id, turn=turn)
