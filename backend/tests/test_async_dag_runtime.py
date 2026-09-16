from __future__ import annotations

import asyncio

import pytest

from app.schemas.composition import (
    CompositionCondition,
    CompositionEdge,
    CompositionNode,
    CompositionPlan,
)
from app.services.async_dag_runtime import (
    AsyncDagRuntime,
    BudgetExceededError,
    NodeTimeoutError,
)


def _plan(nodes, edges=None):
    return CompositionPlan(plan_id="p1", nodes=nodes, edges=edges or [])


@pytest.mark.asyncio
async def test_independent_nodes_run_concurrently():
    ready = asyncio.Event()
    active = 0

    async def handler(inputs):
        nonlocal active
        active += 1
        if active == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=0.5)
        return inputs

    runtime = AsyncDagRuntime(max_concurrency=2)
    result = await runtime.execute(
        _plan(
            [
                CompositionNode(node_id="a", module_id="a", input_bindings={"value": 1}),
                CompositionNode(node_id="b", module_id="b", input_bindings={"value": 2}),
            ]
        ),
        handlers={"a": handler, "b": handler},
    )
    assert result.node_results["a"]["value"] == 1
    assert result.node_results["b"]["value"] == 2


@pytest.mark.asyncio
async def test_dependent_node_receives_upstream_output():
    async def source(_inputs):
        return {"value": 7}

    async def target(inputs):
        return {"value": inputs["value"] + 1}

    result = await AsyncDagRuntime().execute(
        _plan(
            [
                CompositionNode(node_id="a", module_id="a"),
                CompositionNode(node_id="b", module_id="b"),
            ],
            [CompositionEdge(from_node="a", from_output="value", to_node="b", to_input="value")],
        ),
        handlers={"a": source, "b": target},
    )
    assert result.node_results["b"]["value"] == 8


@pytest.mark.asyncio
async def test_node_timeout_is_enforced():
    async def slow(_inputs):
        await asyncio.sleep(1)
        return {"value": 1}

    with pytest.raises(NodeTimeoutError):
        await AsyncDagRuntime().execute(
            _plan([CompositionNode(node_id="a", module_id="a", timeout_ms=20)]),
            handlers={"a": slow},
        )


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure():
    calls = 0

    async def flaky(_inputs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("transient")
        return {"value": "ok"}

    result = await AsyncDagRuntime().execute(
        _plan([CompositionNode(node_id="a", module_id="a", retry_count=2)]),
        handlers={"a": flaky},
    )
    assert result.node_results["a"]["value"] == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_bounded_concurrency_respected():
    active = 0
    max_active = 0

    async def handler(value):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.03)
        active -= 1
        return {"value": value}

    plan = _plan(
        [
            CompositionNode(node_id=f"n{i}", module_id=f"n{i}", input_bindings={"value": i})
            for i in range(5)
        ]
    )
    await AsyncDagRuntime(max_concurrency=2).execute(
        plan,
        handlers={f"n{i}": handler for i in range(5)},
    )
    assert max_active <= 2


@pytest.mark.asyncio
async def test_cache_hit_skips_handler():
    cache: dict[str, dict] = {}
    calls = 0

    async def cache_get(key):
        return cache.get(key)

    async def cache_set(key, value, ttl_seconds=300):
        cache[key] = value

    async def handler(inputs):
        nonlocal calls
        calls += 1
        return {"value": inputs["value"]}

    runtime = AsyncDagRuntime(cache_get=cache_get, cache_set=cache_set)
    plan = _plan(
        [CompositionNode(node_id="a", module_id="a", input_bindings={"value": 3})]
    )
    first = await runtime.execute(plan, handlers={"a": handler})
    second = await runtime.execute(plan, handlers={"a": handler})
    assert first.node_results["a"]["value"] == 3
    assert second.node_results["a"]["value"] == 3
    assert calls == 1
    assert second.cache_hits == ["a"]


@pytest.mark.asyncio
async def test_partial_failure_keeps_independent_results():
    async def good(_inputs):
        return {"value": 1}

    async def bad(_inputs):
        raise RuntimeError("failed")

    result = await AsyncDagRuntime().execute(
        _plan(
            [
                CompositionNode(node_id="a", module_id="a"),
                CompositionNode(node_id="b", module_id="b"),
            ]
        ),
        handlers={"a": good, "b": bad},
        allow_partial=True,
    )
    assert result.node_results["a"]["value"] == 1
    assert result.failed_nodes == ["b"]


@pytest.mark.asyncio
async def test_condition_false_skips_node_and_dependents():
    async def source(_inputs):
        return {"level": "low"}

    async def skipped(_inputs):
        raise AssertionError("conditional node should not execute")

    result = await AsyncDagRuntime().execute(
        _plan(
            [
                CompositionNode(node_id="source", module_id="source"),
                CompositionNode(
                    node_id="conditional",
                    module_id="conditional",
                    condition=CompositionCondition(
                        source_node="source",
                        source_output="level",
                        operator="eq",
                        value="high",
                    ),
                ),
                CompositionNode(node_id="dependent", module_id="dependent"),
            ],
            [
                CompositionEdge(
                    from_node="conditional",
                    from_output="value",
                    to_node="dependent",
                    to_input="value",
                )
            ],
        ),
        handlers={"source": source, "conditional": skipped, "dependent": skipped},
    )
    assert result.node_results["source"]["level"] == "low"
    assert result.skipped_nodes == ["conditional", "dependent"]


@pytest.mark.asyncio
async def test_runtime_enforces_cost_budget():
    async def handler(_inputs):
        return {"value": 1}

    with pytest.raises(BudgetExceededError):
        await AsyncDagRuntime(max_cost=1.0).execute(
            _plan(
                [
                    CompositionNode(node_id="a", module_id="a", cost_estimate=0.8),
                    CompositionNode(node_id="b", module_id="b", cost_estimate=0.8),
                ]
            ),
            handlers={"a": handler, "b": handler},
        )
