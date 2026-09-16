"""Execute validated multi-metric composition plans through the async DAG runtime."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.schemas.claim import Claim, claims_to_dict
from app.schemas.composition import CompositionPlan
from app.schemas.conversation_route import ConversationPolicy, ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.semantic_turn import SemanticTurnResult
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.async_dag_runtime import AsyncDagRuntime
from app.services import cache_service
from app.services.composition_catalog import build_composition_catalog
from app.services.composition_planner import plan_from_frame
from app.services.composition_validator import validate_composition_plan
from app.services.semantic_tool_executors import build_semantic_tool_executors


def _build_plan(frame: SemanticFrame, snapshot) -> CompositionPlan | None:
    catalog = build_composition_catalog(snapshot)
    candidates = [f"metric_{metric}" for metric in frame.metrics]
    return plan_from_frame(frame=frame, candidates=candidates, modules=catalog)


async def execute_metric_composition(
    *,
    frame: SemanticFrame,
    route: ConversationRoute,
    policy: ConversationPolicy,
    query: str,
    session_id: str,
    snapshot,
    session_factory,
    executor_factory: Callable[..., dict[str, Callable[..., Any]]] | None = None,
    max_concurrency: int = 4,
) -> SemanticTurnResult | None:
    if len(frame.metrics) < 2 or session_factory is None:
        return None
    plan = _build_plan(frame, snapshot)
    if plan is None:
        return None
    plan.metadata["cache_scope"] = f"session:{session_id}"

    make_executors = executor_factory or build_semantic_tool_executors

    def handler_for(module_id: str):
        async def execute(inputs: dict[str, Any]) -> dict[str, Any]:
            async with session_factory() as node_db:
                executors = make_executors(db=node_db, session_id=session_id)
                executor = executors.get(module_id)
                if executor is None:
                    raise RuntimeError(f"executor not found: {module_id}")
                params = {**inputs, "query": f"{query} {inputs.get('query') or ''}".strip()}
                return await executor(params=params, dependency_results={})

        return execute

    handlers = {node.module_id: handler_for(node.module_id) for node in plan.nodes}
    execution = await AsyncDagRuntime(
        max_concurrency=max_concurrency,
        cache_get=cache_service.get,
        cache_set=cache_service.set,
    ).execute(
        plan,
        handlers=handlers,
        allow_partial=True,
    )
    claims: list[Claim] = []
    followups: list[str] = []
    for output in execution.node_results.values():
        claims.extend(Claim.model_validate(item) for item in output.get("claims") or [])
        for item in output.get("followups") or []:
            if isinstance(item, str) and item not in followups:
                followups.append(item)
    if not claims:
        return None

    from app.services import llm_reply

    reply, _bundle, reply_source = await llm_reply.generate_claim_reply(
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
    tool_plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id=node.node_id,
                tool_id=node.module_id,
                params=node.input_bindings,
            )
            for node in plan.nodes
        ],
    )
    return SemanticTurnResult(
        status="answered",
        route=route,
        policy=policy,
        claims=claims,
        plan=tool_plan,
        reply=reply,
        followups=followups,
        reply_source=reply_source,
        meta={
            "composition_plan_id": plan.plan_id,
            "composition_completed_order": execution.completed_order,
            "composition_elapsed_ms": execution.elapsed_ms,
            "composition_cache_hits": execution.cache_hits,
            "composition_failed_nodes": execution.failed_nodes,
            "composition_claims": claims_to_dict(claims),
        },
    )
