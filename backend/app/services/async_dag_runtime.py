"""Bounded asynchronous executor for validated composition DAGs."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.composition import CompositionPlan


NodeHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class DagRuntimeError(RuntimeError):
    pass


class NodeTimeoutError(DagRuntimeError):
    pass


class NodeExecutionError(DagRuntimeError):
    pass


class BudgetExceededError(DagRuntimeError):
    pass


class AsyncDagExecutionResult(BaseModel):
    node_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    completed_order: list[str] = Field(default_factory=list)
    cache_hits: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    skipped_nodes: list[str] = Field(default_factory=list)
    total_cost: float = 0.0
    elapsed_ms: float = 0.0


class AsyncDagRuntime:
    def __init__(
        self,
        max_concurrency: int = 8,
        *,
        cache_get: Callable[[str], Awaitable[Any | None]] | None = None,
        cache_set: Callable[..., Awaitable[None]] | None = None,
        cache_ttl_seconds: int = 300,
        max_cost: float | None = None,
        max_nodes: int | None = None,
    ):
        self.max_concurrency = max(1, int(max_concurrency or 1))
        self.cache_get = cache_get
        self.cache_set = cache_set
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_cost = max_cost
        self.max_nodes = max_nodes

    @staticmethod
    def _condition_matches(condition, value: Any) -> bool:
        expected = condition.value
        return {
            "eq": value == expected,
            "ne": value != expected,
            "gt": value > expected,
            "gte": value >= expected,
            "lt": value < expected,
            "lte": value <= expected,
            "truthy": bool(value),
            "falsy": not bool(value),
        }[condition.operator]

    def _cache_key(
        self,
        plan: CompositionPlan,
        node,
        inputs: dict[str, Any],
    ) -> str:
        payload = json.dumps(inputs, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        scope = plan.metadata.get("cache_scope") or "global"
        return f"composition:node:{scope}:{node.module_id}:{digest}"

    def _bind_inputs(
        self,
        plan: CompositionPlan,
        node_id: str,
        results: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], bool]:
        node = next(item for item in plan.nodes if item.node_id == node_id)
        inputs = dict(node.input_bindings)
        for edge in plan.edges:
            if edge.to_node != node_id:
                continue
            source = results[edge.from_node]
            if edge.from_output not in source:
                raise NodeExecutionError(
                    f"missing upstream output {edge.from_node}.{edge.from_output}"
                )
            inputs[edge.to_input] = source[edge.from_output]
        return inputs

    async def _invoke(
        self,
        handler: NodeHandler,
        inputs: dict[str, Any],
        *,
        timeout_ms: int,
    ) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(handler(inputs), timeout=timeout_ms / 1000)
        except asyncio.TimeoutError as exc:
            raise NodeTimeoutError(f"node timed out after {timeout_ms}ms") from exc

    async def _run_node(
        self,
        plan: CompositionPlan,
        node_id: str,
        handlers: dict[str, NodeHandler],
        results: dict[str, dict[str, Any]],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        node = next(item for item in plan.nodes if item.node_id == node_id)
        handler = handlers.get(node.module_id)
        if handler is None:
            raise NodeExecutionError(f"handler not found: {node.module_id}")
        inputs = self._bind_inputs(plan, node_id, results)
        cache_key = self._cache_key(plan, node, inputs)
        if self.cache_get is not None:
            cached = await self.cache_get(cache_key)
            if cached is not None:
                return cached, True

        last_error: Exception | None = None
        for _attempt in range(node.retry_count + 1):
            try:
                async with semaphore:
                    output = await self._invoke(handler, inputs, timeout_ms=node.timeout_ms)
                    if self.cache_set is not None:
                        await self.cache_set(
                            cache_key,
                            output,
                            ttl_seconds=self.cache_ttl_seconds,
                        )
                    return output, False
            except Exception as exc:
                last_error = exc

        fallback_handler = handlers.get(node.fallback_module_id or "")
        if fallback_handler is not None:
            async with semaphore:
                output = await self._invoke(
                    fallback_handler,
                    inputs,
                    timeout_ms=node.timeout_ms,
                )
                if self.cache_set is not None:
                    await self.cache_set(
                        cache_key,
                        output,
                        ttl_seconds=self.cache_ttl_seconds,
                    )
                return output, False
        if isinstance(last_error, DagRuntimeError):
            raise last_error
        raise NodeExecutionError(str(last_error)) from last_error

    async def execute(
        self,
        plan: CompositionPlan,
        *,
        handlers: dict[str, NodeHandler],
        allow_partial: bool = False,
        execution_id: str | None = None,
        checkpoint_load: Callable[[str], Awaitable[dict[str, Any] | None]] | None = None,
        checkpoint_save: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> AsyncDagExecutionResult:
        started = time.perf_counter()
        node_ids = [node.node_id for node in plan.nodes]
        if self.max_nodes is not None and len(node_ids) > self.max_nodes:
            raise BudgetExceededError(
                f"node budget exceeded: {len(node_ids)} > {self.max_nodes}"
            )
        dependencies: dict[str, set[str]] = defaultdict(set)
        for node in plan.nodes:
            dependencies[node.node_id].update(node.depends_on)
            if node.condition is not None:
                dependencies[node.node_id].add(node.condition.source_node)
        for edge in plan.edges:
            dependencies[edge.to_node].add(edge.from_node)

        checkpoint = None
        if execution_id and checkpoint_load is not None:
            checkpoint = await checkpoint_load(execution_id)
        results: dict[str, dict[str, Any]] = dict(
            (checkpoint or {}).get("node_results") or {}
        )
        completed: list[str] = list((checkpoint or {}).get("completed_order") or [])
        cache_hits: list[str] = list((checkpoint or {}).get("cache_hits") or [])
        failed_nodes: list[str] = list((checkpoint or {}).get("failed_nodes") or [])
        failed: set[str] = set(failed_nodes)
        skipped_nodes: list[str] = list((checkpoint or {}).get("skipped_nodes") or [])
        skipped: set[str] = set(skipped_nodes)
        total_cost = float((checkpoint or {}).get("total_cost") or 0.0)
        pending = set(node_ids) - set(completed) - failed - skipped
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def save_checkpoint() -> None:
            if execution_id and checkpoint_save is not None:
                await checkpoint_save(
                    execution_id,
                    {
                        "node_results": results,
                        "completed_order": completed,
                        "cache_hits": cache_hits,
                        "failed_nodes": failed_nodes,
                        "skipped_nodes": skipped_nodes,
                        "total_cost": total_cost,
                    },
                )

        while pending:
            dependency_skipped = [
                node_id
                for node_id in node_ids
                if node_id in pending and dependencies[node_id] & skipped
            ]
            for node_id in dependency_skipped:
                pending.remove(node_id)
                skipped.add(node_id)
                skipped_nodes.append(node_id)
            dependency_failed = [
                node_id
                for node_id in node_ids
                if node_id in pending and dependencies[node_id] & failed
            ]
            if dependency_failed and not allow_partial:
                raise DagRuntimeError(
                    f"dependency failed for nodes: {', '.join(dependency_failed)}"
                )
            for node_id in dependency_failed:
                pending.remove(node_id)
                failed.add(node_id)
                failed_nodes.append(node_id)
            if not pending:
                break
            ready = [
                node_id
                for node_id in node_ids
                if node_id in pending and dependencies[node_id].issubset(results)
            ]
            if not ready:
                raise DagRuntimeError("composition plan contains a cycle")
            runnable: list[str] = []
            for node_id in ready:
                node = next(item for item in plan.nodes if item.node_id == node_id)
                if node.condition is None:
                    runnable.append(node_id)
                    continue
                source = results[node.condition.source_node]
                actual = source.get(node.condition.source_output)
                if self._condition_matches(node.condition, actual):
                    runnable.append(node_id)
                else:
                    pending.remove(node_id)
                    skipped.add(node_id)
                    skipped_nodes.append(node_id)
            ready = runnable
            if not ready:
                continue
            outcomes = await asyncio.gather(
                *(
                    self._run_node(plan, node_id, handlers, results, semaphore)
                    for node_id in ready
                ),
                return_exceptions=allow_partial,
            )
            for node_id, outcome in zip(ready, outcomes, strict=True):
                if isinstance(outcome, Exception):
                    failed.add(node_id)
                    failed_nodes.append(node_id)
                    pending.remove(node_id)
                    if not allow_partial:
                        raise outcome
                    continue
                output, cache_hit = outcome
                results[node_id] = output
                completed.append(node_id)
                if cache_hit:
                    cache_hits.append(node_id)
                else:
                    node = next(item for item in plan.nodes if item.node_id == node_id)
                    total_cost += float(node.cost_estimate or 0.0)
                    if self.max_cost is not None and total_cost > self.max_cost:
                        raise BudgetExceededError(
                            f"cost budget exceeded: {total_cost} > {self.max_cost}"
                        )
                pending.remove(node_id)
            await save_checkpoint()

        return AsyncDagExecutionResult(
            node_results=results,
            completed_order=completed,
            cache_hits=cache_hits,
            failed_nodes=failed_nodes,
            skipped_nodes=skipped_nodes,
            total_cost=round(total_cost, 6),
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        )
