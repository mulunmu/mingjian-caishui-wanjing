"""Primary semantic dialogue orchestration for all supported route kinds."""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from app.db.urls import get_sync_engine
from app.db.session import get_async_session_factory
from app.schemas.claim import Claim, ClaimTrace, ClaimValue, claims_to_dict
from app.schemas.composition import CompositionPlan
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
from app.services.route_normalize import is_industry_distribution_query, normalize_route
from app.services.composition_execution_bridge import execute_metric_composition
from app.services.analysis_patterns import ANALYSIS_PATTERNS
from app.services.hybrid_tool_rag import retrieve_tools_hybrid
from app.services.semantic_planner import (
    semantic_plan_to_frame,
)
from app.schemas.semantic_plan import SemanticPlan
from app.services.semantic_answer_composer import (
    compose_semantic_turn,
    resolve_enterprise_entities,
)
from app.services.semantic_frame import frame_from_route
from app.services.semantic_report_flow import (
    build_custom_report_turn,
    build_fixed_report_turn,
)
from app.services.semantic_turn_persistence import persist_primary_turn
from app.services import inventory_scope, scope_state, session_store
from app.services import llm_reply
from app.services.shadow_integration import dialog_act_to_raw_route
from app.services.sync_runner import run_blocking
from app.services.topic_memory import (
    compose_memory_context_blocking,
    looks_like_topic_reference,
    resolve_topic_reference_blocking,
)
from app.services.tool_rag import load_tool_snapshot
from app.services.progress import emit_progress
from app.services.number_norm import normalize_indexed_entity


logger = logging.getLogger(__name__)


class PrimaryContractError(RuntimeError):
    """Raised when a primary handler violates the formal-response contract."""


def promote_route_with_frame(route, frame):
    if (
        (len(frame.metrics) >= 2 or frame.task_type == "open_overview")
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

_OPEN_OVERVIEW_FALLBACK_TOOL_IDS = (
    "metric_overall_score",
    "metric_industry_score",
    "metric_authenticity_score",
    "metric_tax_health_score",
    "metric_invoice_score",
    "metric_finance_score",
    "metric_red_invoice_cnt",
)

_PATTERN_CANDIDATE_PRIORITY = {
    "stratification": (
        "metric_industry_score",
        "metric_credit_level",
        "metric_overall_score",
        "metric_tax_health_score",
        "metric_authenticity_score",
        "metric_invoice_score",
    ),
    "ranking": (
        "metric_overall_score",
        "metric_credit_level",
        "metric_industry_score",
        "metric_fraud_composite_score",
    ),
    "trend": (
        "metric_revenue_yoy",
        "metric_profit_yoy",
        "metric_tax_on_time_rate",
        "metric_change_cnt",
    ),
    "benchmark": (
        "metric_peer_industry_percentile",
        "metric_industry_score",
        "metric_overall_score",
    ),
    "anomaly": (
        "metric_red_invoice_cnt",
        "metric_tax_arrears_cnt",
        "metric_revenue_deviation",
        "metric_suspicious_count",
    ),
}


def _prioritize_candidates(
    candidate_tool_ids: list[str], analysis_pattern: str
) -> list[str]:
    priority = list(_PATTERN_CANDIDATE_PRIORITY.get(analysis_pattern, ()))
    return [tool_id for tool_id in priority if tool_id in candidate_tool_ids] + [
        tool_id for tool_id in candidate_tool_ids if tool_id not in priority
    ]


async def _build_profile_turn(*, db, route, policy, dialog_act, current_eid: str | None):
    payload = await inventory_scope.subject_profile_answer(db, subject_ref=dialog_act.get('subject_ref'), current_eid=current_eid)
    profile = payload.get('meta', {}).get('profile') or {}
    return SemanticTurnResult(status='answered', route=route, policy=policy, claims=list(payload.get('claims') or []), reply=str(payload.get('reply') or ''), followups=[], reply_source='profile', meta={'function': 'profile', 'profile': profile, 'profile_subject': profile})


async def _build_inventory_turn(*, db, route, policy, dialog_act):
    dimension = str(dialog_act.get('inventory_dimension') or '').strip()
    if dimension in {'industry', 'province'}:
        payload = await inventory_scope.dimension_inventory_answer(db, dimension=dimension, industry_l1=dialog_act.get('industry_l1'), province=dialog_act.get('province'))
    else:
        payload = await inventory_scope.inventory_answer(db, ask_kind=dialog_act.get('ask_kind'), industry_l1=dialog_act.get('industry_l1'), province=dialog_act.get('province'))
    items = list(payload.get('followup_items') or [])
    return SemanticTurnResult(status='answered', route=route, policy=policy, claims=list(payload.get('claims') or []), reply=str(payload.get('reply') or ''), followups=[str(x.get('label') or '') for x in items if isinstance(x, dict) and x.get('label')], reply_source='inventory', meta={'function': 'inventory', 'followup_items': items, 'charts': list(payload.get('charts') or []), 'inventory_focus': payload.get('inventory_focus'), 'inventory': payload.get('meta') or {}})


def _is_group_comparison(frame) -> bool:
    values = (frame.filters or {}).get("industry_l1")
    return frame.analysis_pattern == "comparison" and isinstance(values, list) and len(values) > 1


def _comparison_claims_from_groups(claims: list[Claim], groups: list[str]) -> list[Claim]:
    """Build deterministic group-vs-group claims from already-computed metrics."""
    from app.services.metric_registry import format_surface_number, zh_metric_label

    by_metric: dict[str, dict[str, Claim]] = {}
    for claim in claims:
        group = next(
            (
                str(item).split("=", 1)[1]
                for item in (claim.evidence_chain or [])
                if str(item).startswith("industry_group=")
            ),
            "",
        )
        metric = str((claim.value.metric if claim.value else "") or "")
        if group and metric and claim.value and claim.value.number is not None:
            by_metric.setdefault(metric, {}).setdefault(group, claim)

    out: list[Claim] = []
    for metric, per_group in by_metric.items():
        if len(per_group) < 2:
            continue
        label = zh_metric_label(metric) or metric
        parts: list[str] = []
        for group in groups:
            claim = per_group.get(group)
            if not claim or not claim.value:
                continue
            number = format_surface_number(claim.value.number, claim.value.unit or "", metric=metric)
            parts.append(f"{group} {number}{claim.value.unit or ''}")
        if len(parts) < 2:
            continue
        out.append(
            Claim(
                claim=f"{label}对比：{'；'.join(parts)}。",
                value=ClaimValue(metric=f"compare_{metric}", number=None, unit=""),
                trace=ClaimTrace(table="assessment", field=metric, query_id=f"Q_group_compare_{metric}"),
                confidence="computed",
                evidence_chain=[f"groups={','.join(groups)}"],
            )
        )
    return out


async def _execute_group_comparison(
    *, frame, route, policy, query: str, session_id: str, owner: str | None, snapshot
) -> SemanticTurnResult | None:
    groups = [str(item) for item in ((frame.filters or {}).get("industry_l1") or []) if item]
    if len(groups) < 2:
        return None
    candidate_tool_ids = [f"metric_{metric}" for metric in frame.metrics]
    if not candidate_tool_ids:
        candidate_tool_ids = _open_overview_fallback_tool_ids(snapshot)

    grouped_claims: list[Claim] = []
    followups: list[str] = []
    for group in groups:
        group_frame = frame.model_copy(
            update={
                "filters": {**(frame.filters or {}), "industry_l1": group},
                "task_type": "distribution",
                "analysis_pattern": "stratification",
            }
        )
        turn = await execute_metric_composition(
            frame=group_frame,
            route=route,
            policy=policy,
            query=f"{query} {group}",
            session_id=f"{session_id}:industry:{group}",
            owner=owner,
            snapshot=snapshot,
            candidate_tool_ids=candidate_tool_ids,
            session_factory=get_async_session_factory(),
            max_concurrency=4,
            max_cost=10.0,
        )
        if turn is None:
            continue
        for claim in turn.claims:
            grouped_claims.append(
                claim.model_copy(
                    update={
                        "evidence_chain": [
                            *(claim.evidence_chain or []),
                            f"industry_group={group}",
                        ]
                    }
                )
            )
        for item in turn.followups:
            if item not in followups:
                followups.append(item)
    if not grouped_claims:
        return None
    comparison_claims = _comparison_claims_from_groups(grouped_claims, groups)
    if not comparison_claims:
        return None
    claims = comparison_claims + grouped_claims
    from app.services import llm_reply

    reply, _bundle, reply_source = await llm_reply.generate_claim_reply(query, claims, followups)
    prefix = "对比结论：" + "".join(claim.claim or "" for claim in comparison_claims[:2])
    if reply and not all(group in reply for group in groups[:2]):
        reply = f"{prefix}\n{reply}"
    return SemanticTurnResult(
        status="answered",
        route=route,
        policy=policy,
        claims=claims,
        reply=reply or prefix,
        followups=followups[:6],
        reply_source=reply_source,
        meta={"charts": [], "comparison_groups": groups, "comparison_claim_count": len(comparison_claims)},
    )

_COHORT_SCENARIO_PATTERNS = (
    ("warn", re.compile(r"信号最多|哪里信号|预警|异常最多|哪里不对劲|风险最多")),
    ("audit", re.compile(r"可疑|稽查|该查|优先核查|核查")),
    ("rating", re.compile(r"按行业|行业.*风险|风险等级|评级|信用等级")),
    ("warn", re.compile(r"税务情况|财务情况|发票情况|真实性情况|经营情况|风险情况|信用情况|行业地位|税票|舞弊|税负|准时率")),
)


def contextual_cohort_route(query: str, dialogue_state: dict | None) -> dict | None:
    """Force cohort-scope followups onto the matching group scenario."""
    state = dialogue_state or {}
    if state.get("scope") != "cohort":
        return None
    text = query or ""
    if re.search(r"企业\s*(?:\d+|[零〇一二三四五六七八九十百千万两]+)|这家|该企业|本企业", text):
        return None
    for scenario, pattern in _COHORT_SCENARIO_PATTERNS:
        if pattern.search(text):
            return {
                "route": "analysis",
                "domain": scenario,
                "language": "zh",
                "entities": [],
                "needs_tools": True,
                "needs_clarification": False,
                "confidence": 0.96,
            }
    return None


def _open_overview_fallback_tool_ids(snapshot) -> list[str]:
    available = {tool.tool_id for tool in snapshot.tools}
    return [tool_id for tool_id in _OPEN_OVERVIEW_FALLBACK_TOOL_IDS if tool_id in available]


def _bind_planned_entities(composition_plan, entities: list[str]):
    if composition_plan is None or len(entities or []) != 1:
        return composition_plan
    entity = str(entities[0])
    nodes = []
    changed = False
    for node in composition_plan.nodes:
        bindings = dict(node.input_bindings or {})
        if bindings.get("entity") != entity:
            bindings["entity"] = entity
            changed = True
        nodes.append(node.model_copy(update={"input_bindings": bindings}))
    if not changed:
        return composition_plan
    return composition_plan.model_copy(update={"nodes": nodes})


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
        await emit_progress("authoring", "正在组织回答", "基于受控事实生成自然语言")
        result = await build_non_analysis_turn(route, query, policy=policy)

    if result.status == "not_applicable":
        if route.route in {"analysis", "report"}:
            raise PrimaryContractError(f"no primary policy for route={route.route}")
        result = await build_non_analysis_turn(route, query, policy=policy)
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
        "semantic_planner_status": turn.meta.get("semantic_planner_status"),
        "semantic_planner_attempts": turn.meta.get("semantic_planner_attempts") or 0,
        "semantic_planner_errors": turn.meta.get("semantic_planner_errors") or [],
        "semantic_plan": turn.meta.get("semantic_plan"),
        "semantic_plan_summary": turn.meta.get("semantic_plan_summary"),
        "semantic_composition_plan_id": turn.meta.get(
            "semantic_composition_plan_id"
        ),
        "semantic_composition_tool_ids": turn.meta.get(
            "semantic_composition_tool_ids"
        )
        or [],
        "inventory": turn.meta.get("inventory"),
        "profile": turn.meta.get("profile"),
        "analysis_focus": turn.meta.get("analysis_focus") or {},
        "analysis_pattern": turn.meta.get("analysis_pattern"),
        "comparison_basis": turn.meta.get("comparison_basis"),
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
        "composition_strategy": turn.meta.get("composition_strategy"),
        "composition_selected_tool_ids": turn.meta.get(
            "composition_selected_tool_ids"
        )
        or [],
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
    function = turn.meta.get('function') or turn.route.domain or turn.route.route
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
        "followup_items": list(turn.meta.get("followup_items") or []) or [
            {"type": "query", "label": item, "params": {"query": item}}
            for item in followups
        ],
        "evidence_hidden": True,
        "primary": _primary_meta(turn),
        "analysis_pattern": turn.meta.get("analysis_pattern"),
        "comparison_basis": turn.meta.get("comparison_basis"),
        "analysis_focus": turn.meta.get("analysis_focus") or {},
        "report": turn.meta.get("report"),
        "report_id": turn.meta.get("report_id"),
        "report_hint": turn.meta.get("report_hint"),
        "report_locked": bool(turn.meta.get("report_locked")),
        "actions": list(turn.meta.get("actions") or []),
        "cards": list(turn.meta.get("cards") or []),
        "custom_report": turn.meta.get("custom_report_state"),
        "custom_report_proposal": turn.meta.get("custom_report_proposal"),
        "inventory": turn.meta.get("inventory"),
        "profile": turn.meta.get("profile"),
    }
    charts = turn.meta.get("charts") or []
    chart = charts[0] if isinstance(charts, list) and charts else charts
    visuals = charts if isinstance(charts, list) else ([charts] if isinstance(charts, dict) else [])
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
        "charts": chart,
        "visuals": visuals,
        "data": data,
    }


_ROUTE_PRIORITY = {
    "report": 100,
    "analysis": 90,
    "inventory": 85,
    "profile": 84,
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
    semantic_plan: SemanticPlan | dict | None = None,
    composition_plan: CompositionPlan | dict | None = None,
    planner_meta: dict | None = None,
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
    entity_display_names: dict[str, str] = {}
    referenced = None
    has_topic_reference = looks_like_topic_reference(query)
    session_context = await run_blocking(session_store.get_session, session_id)
    session_dialogue_state = (
        session_context.get("dialogue_state")
        if isinstance(session_context, dict)
        else None
    ) or {}
    focused_dialogue_state = scope_state.merge_query_focus(
        session_dialogue_state, query
    )
    analysis_focus = focused_dialogue_state.get("analysis_focus") or {}
    cohort_route = contextual_cohort_route(query, session_dialogue_state)
    if cohort_route is not None:
        raw_route = cohort_route
    if (
        not enterprise_id
        and isinstance(session_dialogue_state, dict)
        and session_dialogue_state.get("scope") == "individual"
    ):
        enterprise_id = (
            (session_dialogue_state.get("subject") or {}).get("enterprise_id")
        )
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
    custom_act = bool(isinstance(raw_route, dict) and raw_route.get("custom_report"))
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
    focus_values = list(analysis_focus.get("industry_l1_values") or [])
    if not focus_values and analysis_focus.get("industry_l1"):
        focus_values = [str(analysis_focus.get("industry_l1"))]
    focus_filters: dict[str, Any] = {}
    if focus_values:
        focus_filters["industry_l1"] = focus_values if len(focus_values) > 1 else focus_values[0]
    if analysis_focus.get("province"):
        focus_filters["province"] = analysis_focus.get("province")
    if focus_filters and raw_route.get("route") in {"clarify", "capability"}:
        raw_route = {
            **raw_route,
            "route": "analysis",
            "domain": "general",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
            "confidence": 0.94,
        }
    if focus_filters and raw_route.get("route") in {"analysis", "report"}:
        raw_route = {
            **raw_route,
            "filters": {
                **dict(raw_route.get("filters") or {}),
                **focus_filters,
            },
        }
    if raw_route.get('route') not in {'inventory', 'profile'} and (
        is_industry_distribution_query(query) or is_industry_distribution_query(effective_query)
    ):
        enterprise_id = None
        raw_route = {
            **raw_route,
            "route": "analysis",
            "domain": "general",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
            "filters": {"dimension": "industry"},
        }
    route = normalize_route(raw_route, effective_query)
    policy = ConversationPolicyRegistry.resolve(route)
    frame = frame_from_route(route, query=effective_query)
    semantic_plan_obj = (
        semantic_plan
        if isinstance(semantic_plan, SemanticPlan)
        else SemanticPlan.model_validate(semantic_plan)
        if semantic_plan
        else None
    )
    planned_composition = (
        composition_plan
        if isinstance(composition_plan, CompositionPlan)
        else CompositionPlan.model_validate(composition_plan)
        if composition_plan
        else None
    )
    planner_meta = planner_meta or {}
    planner_status = str(
        planner_meta.get("status")
        or ("ok" if semantic_plan_obj is not None else "disabled_or_unavailable")
    )
    planner_attempts = int(planner_meta.get("attempts") or 0)
    planner_errors = list(planner_meta.get("errors") or [])
    planner_clarification = str(planner_meta.get("clarification") or "").strip() or None
    if semantic_plan_obj is not None and semantic_plan_obj.action.value == "analysis":
        if route.route != "analysis":
            route = route.model_copy(
                update={
                    "route": "analysis",
                    "domain": route.domain or "general",
                    "needs_tools": True,
                    "needs_clarification": False,
                }
            )
            policy = ConversationPolicyRegistry.resolve(route)
        await emit_progress(
            "planning",
            "已确定分析组合",
            semantic_plan_obj.plan_summary
            or f"计划执行 {len(semantic_plan_obj.steps)} 个模块",
        )
        frame = semantic_plan_to_frame(
            semantic_plan_obj,
            route=route,
            base=frame,
        )
    elif planner_status == "clarify":
        planner_clarification = planner_clarification or (
            "请补充分析对象、行业或地区，以及想组合查看的指标。"
        )
        route = route.model_copy(
            update={
                "route": "clarify",
                "needs_tools": False,
                "needs_clarification": True,
            }
        )
        policy = ConversationPolicyRegistry.resolve(route)
        frame = frame_from_route(route, query=effective_query)
    if frame.entities:
        source_entities = list(frame.entities)
        resolved_entities = await resolve_enterprise_entities(db, frame.entities)
        if resolved_entities:
            entity_display_names = {
                resolved: (normalize_indexed_entity(source) or source)
                for resolved, source in zip(resolved_entities, source_entities)
            }
            frame = frame.model_copy(update={"entities": resolved_entities})
            planned_composition = _bind_planned_entities(
                planned_composition,
                resolved_entities,
            )
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
        if semantic_plan_obj is not None:
            frame = semantic_plan_to_frame(
                semantic_plan_obj,
                route=route,
                base=frame,
            )
    turn = None
    dialog_act = raw_route.get('dialog_act') if isinstance(raw_route.get('dialog_act'), dict) else {}
    if route.route == 'inventory':
        turn = await _build_inventory_turn(db=db, route=route, policy=policy, dialog_act=dialog_act)
    elif route.route == 'profile':
        current_eid = enterprise_id
        turn = await _build_profile_turn(db=db, route=route, policy=policy, dialog_act=dialog_act, current_eid=current_eid)
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
    is_dynamic_analysis = (
        planned_composition is not None
        or len(frame.metrics) >= 2
        or frame.task_type == "open_overview"
        or frame.analysis_pattern != "metric_lookup"
    )
    if planner_clarification and turn is None:
        turn = SemanticTurnResult(
            status="clarify",
            route=route,
            policy=policy,
            reply=planner_clarification,
            reply_source="semantic_planner",
            meta={
                "semantic_planner_status": "clarify",
                "semantic_planner_attempts": planner_attempts,
                "semantic_planner_errors": planner_errors,
            },
        )
    if (
        route.route == "analysis"
        and _is_group_comparison(frame)
    ):
        try:
            snapshot = await load_tool_snapshot(db)
            await emit_progress("planning", "正在按行业拆分对比", "分别为每个行业执行同一组指标")
            turn = await _execute_group_comparison(
                frame=frame,
                route=route,
                policy=policy,
                query=effective_query,
                session_id=session_id,
                owner=owner,
                snapshot=snapshot,
            )
        except Exception as exc:
            logger.warning("group comparison failed for session %s: %s", session_id, exc)
            turn = None
    if route.route == "analysis" and is_dynamic_analysis and turn is None:
        try:
            snapshot = await load_tool_snapshot(db)
            candidate_tool_ids: list[str] | None = None
            needs_retrieval = planned_composition is None and (
                frame.task_type != "multi_metric"
                or len(frame.metrics) < 2
                or frame.analysis_pattern == "overview"
            )
            if needs_retrieval:
                pattern_spec = ANALYSIS_PATTERNS.get(frame.analysis_pattern)
                pattern_hint = (
                    f"{pattern_spec.label} {pattern_spec.description}"
                    if pattern_spec is not None
                    else frame.analysis_pattern
                )
                await emit_progress("retrieval", "正在检索相关指标", "跨财务、税务、发票、真实性和风险域召回候选")
                overview_query = f"{effective_query} {pattern_hint} 财务 税务 发票 真实性 风险信号 评级"
                overview_candidates = await retrieve_tools_hybrid(
                    db,
                    overview_query,
                    snapshot=snapshot,
                    top_k=20 if frame.analysis_pattern == "overview" else 12,
                    executable_only=True,
                    kinds={"atomic_metric", "composite_metric"},
                )
                candidate_tool_ids = [
                    item.tool_id for item in overview_candidates
                ]
                if len(candidate_tool_ids) < (pattern_spec.min_candidates if pattern_spec else 2):
                    candidate_tool_ids = _open_overview_fallback_tool_ids(snapshot)
                candidate_tool_ids = _prioritize_candidates(
                    candidate_tool_ids, frame.analysis_pattern
                )
                await emit_progress(
                    "planning",
                    "正在组合分析方案",
                    f"已召回 {len(candidate_tool_ids)} 个可执行候选",
                )
            turn = await execute_metric_composition(
                frame=frame,
                route=route,
                policy=policy,
                query=effective_query,
                session_id=session_id,
                owner=owner,
                snapshot=snapshot,
                candidate_tool_ids=candidate_tool_ids,
                composition_plan=planned_composition,
                session_factory=get_async_session_factory(),
                max_concurrency=4,
                max_cost=10.0,
            )
            if turn is not None:
                await emit_progress("execution", "正在汇总分析结论")
        except Exception as exc:
            logger.warning("dynamic composition failed for session %s: %s", session_id, exc)
            turn = None
    if is_dynamic_analysis and turn is None:
        try:
            snapshot = snapshot if "snapshot" in locals() else await load_tool_snapshot(db)
            candidate_tool_ids = _open_overview_fallback_tool_ids(snapshot)
            turn = await execute_metric_composition(
                frame=frame,
                route=route,
                policy=policy,
                query=effective_query,
                session_id=session_id,
                owner=owner,
                snapshot=snapshot,
                candidate_tool_ids=candidate_tool_ids,
                composition_plan=planned_composition,
                session_factory=get_async_session_factory(),
                max_concurrency=4,
                max_cost=10.0,
            )
        except Exception as exc:
            logger.warning(
                "dynamic composition fallback failed for session %s: %s",
                session_id,
                exc,
            )
        if turn is None and frame.task_type == "open_overview":
            raise PrimaryContractError("open overview requires dynamic composition")
    if turn is None:
        turn = await compose_primary_turn(
            db=db,
            session_id=session_id,
            query=effective_query,
            raw_route=raw_route,
        )
    turn.meta["semantic_frame"] = frame.model_dump()
    turn.meta["semantic_planner_status"] = planner_status
    turn.meta["semantic_planner_attempts"] = planner_attempts
    turn.meta["semantic_planner_errors"] = planner_errors
    turn.meta["semantic_plan"] = (
        semantic_plan_obj.model_dump(mode="json")
        if semantic_plan_obj is not None
        else None
    )
    turn.meta["semantic_plan_summary"] = (
        semantic_plan_obj.plan_summary if semantic_plan_obj is not None else None
    )
    if planned_composition is not None:
        turn.meta["semantic_composition_plan_id"] = planned_composition.plan_id
        turn.meta["semantic_composition_tool_ids"] = [
            node.module_id for node in planned_composition.nodes
        ]
    turn.meta["analysis_focus"] = dict(analysis_focus)
    turn.meta["analysis_pattern"] = frame.analysis_pattern
    turn.meta["comparison_basis"] = frame.comparison_basis
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
    if entity_display_names:
        turn.meta["entity_display_names"] = entity_display_names
    if persist:
        await persist_primary_turn(
            db=db,
            session_id=session_id,
            owner=owner,
            query=query,
            turn=turn,
            dialogue_state=focused_dialogue_state,
        )
    return build_primary_chat_response(session_id=session_id, turn=turn)
