"""Semantic answer composer: route -> executable plan -> claims -> guarded reply."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics
from app.schemas.claim import Claim
from app.schemas.conversation_route import ConversationPolicyRegistry
from app.schemas.semantic_turn import SemanticTurnResult
from app.schemas.tool_rag import ToolCandidate
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.plan_execution import execute_tool_plan_async
from app.services.route_normalize import normalize_route
from app.services.semantic_tool_executors import build_semantic_tool_executors
from app.services.hybrid_tool_rag import retrieve_tools_hybrid
from app.services.tool_rag import ToolSnapshot, load_tool_snapshot
from app.services.observability import observe_latency
from app.services.progress import emit_progress


def _numeric_entity_key(value: str) -> str | None:
    from app.services.number_norm import numeric_entity_key

    return numeric_entity_key(value)


async def resolve_enterprise_entities(db: AsyncSession, entities: list[str]) -> list[str]:
    resolved: list[str] = []
    resolved_numeric_keys: set[str] = set()
    for item in entities:
        value = str(item).strip()
        if not value:
            continue
        numeric_key = _numeric_entity_key(value)
        if value.upper().startswith("ENT"):
            if value not in resolved:
                resolved.append(value)
            if numeric_key:
                resolved_numeric_keys.add(numeric_key)
            continue
        if numeric_key and numeric_key in resolved_numeric_keys:
            continue
        row = await db.execute(
            select(CoreMetrics.enterprise_id).where(
                (CoreMetrics.enterprise_id == value)
                | (CoreMetrics.display_name == value)
                | (CoreMetrics.display_label == value)
            )
        )
        enterprise_id = row.scalar_one_or_none()
        if enterprise_id and enterprise_id not in resolved:
            resolved.append(enterprise_id)
    return resolved


def _tool_params(query: str, raw_route: dict, entities: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {"query": query}
    if entities:
        params["entity"] = entities[0]
    filters = raw_route.get("filters")
    if isinstance(filters, dict):
        for key, value in filters.items():
            if value:
                params[key] = value
    return params


def _prefer_dimension_candidate(candidates: list[ToolCandidate], raw_route: dict):
    filters = raw_route.get("filters") if isinstance(raw_route.get("filters"), dict) else {}
    dimension = str(filters.get("dimension") or "")
    if dimension != "industry":
        return candidates
    preferred = next(
        (candidate for candidate in candidates if candidate.tool_id == "metric_industry_score"),
        None,
    )
    if preferred is None:
        return candidates
    return [preferred] + [candidate for candidate in candidates if candidate.tool_id != preferred.tool_id]


async def compose_semantic_turn(
    *,
    db: AsyncSession,
    session_id: str,
    query: str,
    raw_route: dict,
    snapshot: ToolSnapshot | None = None,
) -> SemanticTurnResult:
    route = normalize_route(raw_route, query)
    policy = ConversationPolicyRegistry.resolve(route)
    resolved_entities = await resolve_enterprise_entities(db, route.entities)
    if route.entities and not resolved_entities:
        unknown_route = route.model_copy(
            update={
                "route": "unknown_entity",
                "needs_tools": False,
                "needs_clarification": True,
            }
        )
        return SemanticTurnResult(
            status="clarify",
            route=unknown_route,
            policy=policy,
            reply="未找到对应企业，请确认企业名称或编号。",
        )

    if snapshot is None:
        snapshot = await load_tool_snapshot(db)
    probe_allowed = (
        policy.retrieve_candidates
        or bool(resolved_entities)
        or route.route in {"analysis", "report", "clarify", "capability"}
    )
    retrieval_started = time.perf_counter()
    await emit_progress("retrieval", "正在检索可执行指标")
    candidates = (
        await retrieve_tools_hybrid(
            db,
            query,
            snapshot=snapshot,
            domain=route.domain,
            top_k=5,
            executable_only=True,
            kinds={"atomic_metric", "composite_metric"},
        )
        if probe_allowed
        else []
    )
    observe_latency(
        "semantic_stage_latency_ms",
        (time.perf_counter() - retrieval_started) * 1000,
        {"stage": "retrieval"},
    )
    if route.route in {"capability", "clarify"} and resolved_entities and candidates:
        route = route.model_copy(
            update={
                "route": "analysis",
                "needs_tools": True,
                "needs_clarification": False,
                "confidence": max(float(route.confidence or 0.0), 0.8),
            }
        )
        policy = ConversationPolicyRegistry.resolve(route)
    if not policy.retrieve_candidates:
        return SemanticTurnResult(
            status="not_applicable",
            route=route,
            policy=policy,
            candidates=candidates,
        )
    if route.needs_clarification or policy.response_mode == "clarify":
        return SemanticTurnResult(
            status="clarify",
            route=route,
            policy=policy,
            candidates=candidates,
            reply="请补充企业名称或编号，以及想分析的具体指标。",
        )
    if not candidates:
        return SemanticTurnResult(
            status="abstain",
            route=route,
            policy=policy,
            reply="当前没有匹配到可执行的金融风控指标，请换一种问法或指定企业/指标。",
        )
    candidates = _prefer_dimension_candidate(candidates, raw_route)
    selected = candidates[0]
    params = _tool_params(query, raw_route, resolved_entities)
    if selected.tool_id == "metric_industry_score":
        params["dimension"] = "industry"
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="step_1",
                tool_id=selected.tool_id,
                params=params,
            )
        ],
    )
    executors = build_semantic_tool_executors(db=db, session_id=session_id)
    execution_started = time.perf_counter()
    await emit_progress("execution", "正在执行分析")
    execution = await execute_tool_plan_async(
        plan,
        snapshot,
        executors,
        policy=policy,
    )
    observe_latency(
        "semantic_stage_latency_ms",
        (time.perf_counter() - execution_started) * 1000,
        {"stage": "tool_execution"},
    )
    claims = [Claim.model_validate(item) for item in execution.claims]
    charts: list[dict[str, Any]] = []
    for output in execution.step_outputs.values():
        if not isinstance(output, dict):
            continue
        meta = output.get("meta")
        chart = meta.get("charts") if isinstance(meta, dict) else None
        if isinstance(chart, dict):
            charts.append(chart)
        elif isinstance(chart, list):
            charts.extend(item for item in chart if isinstance(item, dict))
    if not claims:
        return SemanticTurnResult(
            status="abstain",
            route=route,
            policy=policy,
            candidates=candidates,
            plan=plan,
            reply="已识别指标，但当前数据没有形成可用结论。",
        )

    followups: list[str] = []
    for output in execution.step_outputs.values():
        for item in output.get("followups") or []:
            if isinstance(item, str) and item not in followups:
                followups.append(item)

    from app.services import llm_reply

    authoring_started = time.perf_counter()
    await emit_progress("authoring", "正在组织回答")
    reply, bundle, reply_source = await llm_reply.generate_claim_reply(
        query,
        claims,
        followups,
    )
    observe_latency(
        "semantic_stage_latency_ms",
        (time.perf_counter() - authoring_started) * 1000,
        {"stage": "authoring"},
    )
    from app.services.hallucination_guard import apply_chat_hallucination_guard

    guard_started = time.perf_counter()
    reply, _, followups = apply_chat_hallucination_guard(
        reply,
        claims,
        followups=followups,
    )
    observe_latency(
        "semantic_stage_latency_ms",
        (time.perf_counter() - guard_started) * 1000,
        {"stage": "guard"},
    )
    return SemanticTurnResult(
        status="answered",
        route=route,
        policy=policy,
        candidates=candidates,
        plan=plan,
        claims=claims,
        reply=reply,
        followups=followups,
        reply_source=reply_source,
        meta={"step_outputs": execution.step_outputs, "charts": charts},
    )
