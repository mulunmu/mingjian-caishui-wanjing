"""Execute validated multi-metric composition plans through the async DAG runtime."""
from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
from typing import Any

from app.schemas.claim import Claim, ClaimTrace, ClaimValue, claims_to_dict
from app.schemas.composition import CompositionPlan
from app.schemas.conversation_route import ConversationPolicy, ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.semantic_turn import SemanticTurnResult
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.async_dag_runtime import AsyncDagRuntime
from app.services import cache_service
from app.db.urls import get_sync_engine
from app.services.composition_blueprint_store import (
    save_composition_blueprint_sync,
    snapshot_registry_version,
)
from app.services.composition_checkpoint_store import (
    load_checkpoint_sync,
    save_checkpoint_sync,
)
from app.services.composition_catalog import build_composition_catalog
from app.services.composition_planner import build_composition_plan, plan_from_frame
from app.services.composition_validator import validate_composition_plan
from app.services.semantic_tool_executors import build_semantic_tool_executors
from app.services.sync_runner import run_blocking


def _build_plan(
    frame: SemanticFrame,
    snapshot,
    *,
    candidate_tool_ids: list[str] | None = None,
) -> CompositionPlan | None:
    catalog = build_composition_catalog(snapshot)
    candidates = list(candidate_tool_ids or []) or [
        f"metric_{metric}" for metric in frame.metrics
    ]
    if (
        len(candidates) == 1
        and frame.analysis_pattern in {"comparison", "stratification"}
    ):
        return build_composition_plan(
            frame=frame.model_dump(),
            candidates=candidates,
            pattern="metric_lookup",
            modules=catalog,
        )
    return plan_from_frame(frame=frame, candidates=candidates, modules=catalog)


def _semantic_group_bindings(node) -> dict[str, str]:
    bindings = node.input_bindings or {}
    groups: dict[str, str] = {}
    for key in ("industry_l1", "province", "city"):
        value = bindings.get(key)
        if isinstance(value, list):
            value = value[0] if len(value) == 1 else None
        if value not in (None, ""):
            groups[key] = str(value)
    return groups


def _comparison_claims_from_semantic_nodes(
    claims: list[Claim],
    *,
    group_by: str,
    groups: list[str],
) -> list[Claim]:
    from app.services.metric_registry import format_surface_number, zh_metric_label

    by_metric: dict[str, dict[str, Claim]] = {}
    for claim in claims:
        chain = [str(item) for item in (claim.evidence_chain or [])]
        group = next(
            (
                item.split("=", 1)[1]
                for item in chain
                if item.startswith(f"semantic_group_{group_by}=")
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
            number = format_surface_number(
                claim.value.number,
                claim.value.unit or "",
                metric=metric,
            )
            parts.append(f"{group} {number}{claim.value.unit or ''}")
        if len(parts) < 2:
            continue
        out.append(
            Claim(
                claim=f"{label}对比：{'；'.join(parts)}。",
                value=ClaimValue(metric=f"compare_{metric}", number=None, unit=""),
                trace=ClaimTrace(
                    table="composition",
                    field=metric,
                    query_id=f"Q_semantic_compare_{metric}",
                ),
                confidence="computed",
                evidence_chain=[
                    f"group_by={group_by}",
                    f"groups={','.join(groups)}",
                    f"source_metric={metric}",
                ],
            )
        )
    return out


async def execute_metric_composition(
    *,
    frame: SemanticFrame,
    route: ConversationRoute,
    policy: ConversationPolicy,
    query: str,
    session_id: str,
    owner: str | None = None,
    snapshot,
    session_factory,
    candidate_tool_ids: list[str] | None = None,
    composition_plan: CompositionPlan | None = None,
    executor_factory: Callable[..., dict[str, Callable[..., Any]]] | None = None,
    max_concurrency: int = 4,
    max_cost: float | None = 5.0,
) -> SemanticTurnResult | None:
    if session_factory is None:
        return None
    if composition_plan is not None:
        catalog = build_composition_catalog(snapshot)
        if not validate_composition_plan(composition_plan, catalog).valid:
            return None
        plan = composition_plan
    else:
        dynamic_candidates = list(candidate_tool_ids or [])
        if (
            frame.task_type != "open_overview"
            and len(frame.metrics) < 2
            and len(dynamic_candidates) < 2
            and not (
                len(dynamic_candidates) == 1
                and frame.analysis_pattern in {"comparison", "stratification"}
            )
        ):
            return None
        plan = _build_plan(
            frame,
            snapshot,
            candidate_tool_ids=candidate_tool_ids,
        )
    if plan is None:
        return None
    plan.metadata["cache_scope"] = f"session:{session_id}:executor-v22"
    registry_version = snapshot_registry_version(snapshot)
    execution_id = hashlib.sha256(
        f"{session_id}:{plan.plan_id}:{query}:executor-v22".encode("utf-8")
    ).hexdigest()[:24]
    blueprint_persisted = False
    try:
        await run_blocking(
            save_composition_blueprint_sync,
            get_sync_engine(),
            plan,
            registry_version=registry_version,
            owner=owner,
            session_id=session_id,
        )
        blueprint_persisted = True
    except Exception:
        blueprint_persisted = False

    make_executors = executor_factory or build_semantic_tool_executors

    def handler_for(module_id: str):
        async def execute(inputs: dict[str, Any]) -> dict[str, Any]:
            async with session_factory() as node_db:
                executors = make_executors(db=node_db, session_id=session_id)
                executor = executors.get(module_id)
                if executor is None:
                    raise RuntimeError(f"executor not found: {module_id}")
                params = {**inputs, "query": f"{query} {inputs.get('query') or ''}".strip()}
                result = await executor(params=params, dependency_results={})
                if module_id.startswith("metric_"):
                    claim_items = result.get("claims") or []
                    for claim in claim_items:
                        value = claim.get("value") if isinstance(claim, dict) else None
                        if isinstance(value, dict) and value.get("number") is not None:
                            result["value"] = value["number"]
                            break
                return result

        return execute

    handlers = {node.module_id: handler_for(node.module_id) for node in plan.nodes}

    async def load_checkpoint(execution_id_value: str):
        try:
            return await run_blocking(
                load_checkpoint_sync,
                get_sync_engine(),
                execution_id_value,
            )
        except Exception:
            return None

    async def save_checkpoint(execution_id_value: str, state: dict) -> None:
        try:
            await run_blocking(
                save_checkpoint_sync,
                get_sync_engine(),
                execution_id=execution_id_value,
                plan_id=plan.plan_id,
                registry_version=registry_version,
                state=state,
            )
        except Exception:
            return None

    execution = await AsyncDagRuntime(
        max_concurrency=max_concurrency,
        cache_get=cache_service.get,
        cache_set=cache_service.set,
        max_cost=max_cost,
    ).execute(
        plan,
        handlers=handlers,
        allow_partial=True,
        execution_id=execution_id,
        checkpoint_load=load_checkpoint,
        checkpoint_save=save_checkpoint,
    )
    try:
        await run_blocking(
            save_checkpoint_sync,
            get_sync_engine(),
            execution_id=execution_id,
            plan_id=plan.plan_id,
            registry_version=registry_version,
            state={
                "node_results": execution.node_results,
                "completed_order": execution.completed_order,
                "cache_hits": execution.cache_hits,
                "failed_nodes": execution.failed_nodes,
                "skipped_nodes": execution.skipped_nodes,
                "total_cost": execution.total_cost,
            },
            status="completed",
        )
    except Exception:
        pass
    claims: list[Claim] = []
    followups: list[str] = []
    charts: list[dict[str, Any]] = []
    chart_keys: set[str] = set()
    node_map = {node.node_id: node for node in plan.nodes}
    group_values: dict[str, list[str]] = {}
    for node_id, output in execution.node_results.items():
        node = node_map.get(node_id)
        group_bindings = _semantic_group_bindings(node) if node is not None else {}
        for key, value in group_bindings.items():
            values = group_values.setdefault(key, [])
            if value not in values:
                values.append(value)
        claim_items = []
        for item in output.get("claims") or []:
            if not isinstance(item, dict):
                continue
            enriched_item = {**item}
            chain = list(enriched_item.get("evidence_chain") or [])
            if node_id not in chain:
                chain.append(f"semantic_step_id={node_id}")
            for key, value in group_bindings.items():
                marker = f"semantic_group_{key}={value}"
                if marker not in chain:
                    chain.append(marker)
            enriched_item["evidence_chain"] = chain
            claim_items.append(enriched_item)
        node_claims = [Claim.model_validate(item) for item in claim_items]
        claims.extend(node_claims)
        claim_ids = [
            str((claim.trace.query_id if claim.trace else "") or "")
            for claim in node_claims
            if (claim.trace.query_id if claim.trace else "")
        ]
        meta = output.get("meta") if isinstance(output, dict) else None
        chart = meta.get("charts") if isinstance(meta, dict) else None
        chart_items = (
            [chart]
            if isinstance(chart, dict)
            else [item for item in chart if isinstance(item, dict)]
            if isinstance(chart, list)
            else []
        )
        for item in chart_items:
            enriched = {**item}
            if claim_ids:
                enriched["claim_ids"] = claim_ids
            key = json.dumps(enriched, ensure_ascii=False, sort_keys=True, default=str)
            if key not in chart_keys:
                chart_keys.add(key)
                charts.append(enriched)
        for item in output.get("followups") or []:
            if isinstance(item, str) and item not in followups:
                followups.append(item)
    comparison_claims: list[Claim] = []
    group_by = next(
        (key for key, values in group_values.items() if len(values) >= 2),
        None,
    )
    if group_by is not None:
        comparison_claims = _comparison_claims_from_semantic_nodes(
            claims,
            group_by=group_by,
            groups=group_values[group_by],
        )
        if comparison_claims:
            claims = comparison_claims + claims
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
            "composition_skipped_nodes": execution.skipped_nodes,
            "composition_total_cost": execution.total_cost,
            "composition_registry_version": registry_version,
            "composition_blueprint_persisted": blueprint_persisted,
            "composition_execution_id": execution_id,
            "composition_claims": claims_to_dict(claims),
            "semantic_comparison_claims": claims_to_dict(comparison_claims),
            "charts": charts,
            "composition_strategy": plan.metadata.get("strategy"),
            "composition_selected_tool_ids": plan.metadata.get("selected_tool_ids")
            or [node.module_id for node in plan.nodes],
        },
    )
