"""Semantic answer composer: route -> executable plan -> claims -> guarded reply."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics
from app.schemas.claim import Claim
from app.schemas.conversation_route import ConversationPolicyRegistry
from app.schemas.semantic_turn import SemanticTurnResult
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.plan_execution import execute_tool_plan_async
from app.services.route_normalize import normalize_route
from app.services.semantic_tool_executors import build_semantic_tool_executors
from app.services.tool_rag import ToolRagRetriever, ToolSnapshot, load_tool_snapshot


def _numeric_entity_key(value: str) -> str | None:
    import re

    match = re.search(r"(\d+)", value or "")
    return match.group(1).lstrip("0") or "0" if match else None


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
                (CoreMetrics.display_name == value)
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
        return SemanticTurnResult(
            status="clarify",
            route=route,
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
    candidates = (
        ToolRagRetriever(snapshot).retrieve(
            query,
            domain=route.domain,
            top_k=5,
            executable_only=True,
            kinds={"atomic_metric", "composite_metric"},
        )
        if probe_allowed
        else []
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
    selected = candidates[0]
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="step_1",
                tool_id=selected.tool_id,
                params=_tool_params(query, raw_route, resolved_entities),
            )
        ],
    )
    executors = build_semantic_tool_executors(db=db, session_id=session_id)
    execution = await execute_tool_plan_async(
        plan,
        snapshot,
        executors,
        policy=policy,
    )
    claims = [Claim.model_validate(item) for item in execution.claims]
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

    reply, bundle, reply_source = await llm_reply.generate_claim_reply(
        query,
        claims,
        followups,
    )
    from app.services.hallucination_guard import apply_chat_hallucination_guard

    reply, _, followups = apply_chat_hallucination_guard(
        reply,
        claims,
        followups=followups,
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
        meta={"step_outputs": execution.step_outputs},
    )