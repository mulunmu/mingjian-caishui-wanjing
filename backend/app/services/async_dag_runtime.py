"""Bounded asynchronous executor for validated composition DAGs."""
from __future__ import annotations

import asyncio
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


class AsyncDagExecutionResult(BaseModel):
    node_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    completed_order: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0


class AsyncDagRuntime:
    def __init__(self, max_concurrency: int = 8):
        self.max_concurrency = max(1, int(max_concurrency or 1))

    def _bind_inputs(
        self,
        plan: CompositionPlan,
        node_id: str,
        results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
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

        last_error: Exception | None = None
        for _attempt in range(node.retry_count + 1):
            try:
                async with semaphore:
                    return await self._invoke(handler, inputs, timeout_ms=node.timeout_ms)
            except Exception as exc:
                last_error = exc

        fallback_handler = handlers.get(node.fallback_module_id or "")
        if fallback_handler is not None:
            async with semaphore:
                return await self._invoke(
                    fallback_handler,
                    inputs,
                    timeout_ms=node.timeout_ms,
                )
        if isinstance(last_error, DagRuntimeError):
            raise last_error
        raise NodeExecutionError(str(last_error)) from last_error

    async def execute(
        self,
        plan: CompositionPlan,
        *,
        handlers: dict[str, NodeHandler],
    ) -> AsyncDagExecutionResult:
        started = time.perf_counter()
        node_ids = [node.node_id for node in plan.nodes]
        dependencies: dict[str, set[str]] = defaultdict(set)
        for node in plan.nodes:
            dependencies[node.node_id].update(node.depends_on)
        for edge in plan.edges:
            dependencies[edge.to_node].add(edge.from_node)

        pending = set(node_ids)
        results: dict[str, dict[str, Any]] = {}
        completed: list[str] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)

        while pending:
            ready = [
                node_id
                for node_id in node_ids
                if node_id in pending and dependencies[node_id].issubset(results)
            ]
            if not ready:
                raise DagRuntimeError("composition plan contains a cycle")
            outputs = await asyncio.gather(
                *(
                    self._run_node(plan, node_id, handlers, results, semaphore)
                    for node_id in ready
                )
            )
            for node_id, output in zip(ready, outputs, strict=True):
                results[node_id] = output
                completed.append(node_id)
                pending.remove(node_id)

        return AsyncDagExecutionResult(
            node_results=results,
            completed_order=completed,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
        )
