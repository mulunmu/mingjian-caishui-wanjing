"""Deterministic orchestration bake-off: AsyncDagRuntime vs LangGraph 1.x."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any, TypedDict

from app.schemas.composition import CompositionEdge, CompositionNode, CompositionPlan
from app.services.async_dag_runtime import AsyncDagRuntime

try:
    import importlib.metadata

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, RetryPolicy, interrupt

    LANGGRAPH_VERSION = importlib.metadata.version("langgraph")
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover - experiment runner reports the absence
    LANGGRAPH_VERSION = None
    LANGGRAPH_AVAILABLE = False


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio)))], 3)


def _diamond_plan() -> CompositionPlan:
    return CompositionPlan(
        plan_id="bakeoff-diamond",
        nodes=[
            CompositionNode(node_id="start", module_id="start"),
            CompositionNode(node_id="left", module_id="left", depends_on=["start"]),
            CompositionNode(node_id="right", module_id="right", depends_on=["start"]),
            CompositionNode(node_id="join", module_id="join", depends_on=["left", "right"]),
        ],
        edges=[
            CompositionEdge(from_node="start", from_output="value", to_node="left", to_input="source"),
            CompositionEdge(from_node="start", from_output="value", to_node="right", to_input="source"),
            CompositionEdge(from_node="left", from_output="value", to_node="join", to_input="left"),
            CompositionEdge(from_node="right", from_output="value", to_node="join", to_input="right"),
        ],
    )


def _diamond_handlers() -> dict[str, Any]:
    async def start(_: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.002)
        return {"value": 1}

    async def left(inputs: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        return {"value": int(inputs["source"]) + 1}

    async def right(inputs: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.015)
        return {"value": int(inputs["source"]) + 2}

    async def join(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"value": int(inputs["left"]) + int(inputs["right"])}

    return {"start": start, "left": left, "right": right, "join": join}


async def _current_diamond_once() -> tuple[int, float]:
    started = time.perf_counter()
    result = await AsyncDagRuntime(max_concurrency=4).execute(
        _diamond_plan(), handlers=_diamond_handlers()
    )
    return int(result.node_results["join"]["value"]), (time.perf_counter() - started) * 1000


def _merge_values(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**(left or {}), **(right or {})}


class GraphState(TypedDict):
    values: Annotated[dict[str, Any], _merge_values]


def _langgraph_diamond_app():
    async def start(state: GraphState) -> dict[str, Any]:
        await asyncio.sleep(0.002)
        return {"values": {**state.get("values", {}), "start": 1}}

    async def left(state: GraphState) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        return {"values": {**state["values"], "left": int(state["values"]["start"]) + 1}}

    async def right(state: GraphState) -> dict[str, Any]:
        await asyncio.sleep(0.015)
        return {"values": {**state["values"], "right": int(state["values"]["start"]) + 2}}

    async def join(state: GraphState) -> dict[str, Any]:
        values = state["values"]
        return {"values": {**values, "result": int(values["left"]) + int(values["right"])}}

    graph = StateGraph(GraphState)
    graph.add_node("start", start)
    graph.add_node("left", left)
    graph.add_node("right", right)
    graph.add_node("join", join)
    graph.add_edge(START, "start")
    graph.add_edge("start", "left")
    graph.add_edge("start", "right")
    graph.add_edge("left", "join")
    graph.add_edge("right", "join")
    graph.add_edge("join", END)
    return graph.compile()


async def _langgraph_diamond_once(app) -> tuple[int, float]:
    started = time.perf_counter()
    result = await app.ainvoke({"values": {}})
    return int(result["values"]["result"]), (time.perf_counter() - started) * 1000


async def _current_retry_once() -> tuple[int, int]:
    attempts = {"count": 0}

    async def flaky(_: dict[str, Any]) -> dict[str, Any]:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient")
        return {"value": 7}

    plan = CompositionPlan(
        plan_id="bakeoff-retry",
        nodes=[CompositionNode(node_id="flaky", module_id="flaky", retry_count=2, timeout_ms=1000)],
    )
    result = await AsyncDagRuntime().execute(plan, handlers={"flaky": flaky})
    return int(result.node_results["flaky"]["value"]), attempts["count"]


async def _langgraph_retry_once() -> tuple[int, int]:
    attempts = {"count": 0}

    async def flaky(state: GraphState) -> dict[str, Any]:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient")
        return {"values": {**state.get("values", {}), "value": 7}}

    graph = StateGraph(GraphState)
    graph.add_node(
        "flaky",
        flaky,
        retry_policy=RetryPolicy(
            initial_interval=0,
            max_interval=0,
            backoff_factor=1,
            jitter=False,
            max_attempts=3,
            retry_on=RuntimeError,
        ),
    )
    graph.add_edge(START, "flaky")
    graph.add_edge("flaky", END)
    result = await graph.compile().ainvoke({"values": {}})
    return int(result["values"]["value"]), attempts["count"]


async def _current_checkpoint_resume() -> dict[str, Any]:
    calls: list[str] = []
    checkpoint = {
        "node_results": {
            "start": {"value": 1},
            "left": {"value": 2},
            "right": {"value": 3},
        },
        "completed_order": ["start", "left", "right"],
        "cache_hits": [],
        "failed_nodes": [],
        "skipped_nodes": [],
        "total_cost": 0,
    }

    async def load(_: str):
        return checkpoint

    async def save(_: str, value: dict[str, Any]):
        checkpoint.clear()
        checkpoint.update(value)

    handlers = _diamond_handlers()
    wrapped = {}
    for name, handler in handlers.items():
        async def wrapped_handler(inputs, _name=name, _handler=handler):
            calls.append(_name)
            return await _handler(inputs)

        wrapped[name] = wrapped_handler

    result = await AsyncDagRuntime().execute(
        _diamond_plan(),
        handlers=wrapped,
        execution_id="resume-1",
        checkpoint_load=load,
        checkpoint_save=save,
    )
    return {"result": result.node_results["join"]["value"], "executed_nodes": calls}


class ApprovalState(TypedDict):
    value: int
    approved: bool


async def _langgraph_interrupt_resume() -> dict[str, Any]:
    async def begin(state: ApprovalState) -> dict[str, Any]:
        return {"value": 1, "approved": False}

    async def approval(state: ApprovalState) -> dict[str, Any]:
        answer = interrupt({"question": "approve"})
        return {"approved": bool(answer)}

    async def finish(state: ApprovalState) -> dict[str, Any]:
        return {"value": state["value"] + (10 if state["approved"] else 0)}

    graph = StateGraph(ApprovalState)
    graph.add_node("begin", begin)
    graph.add_node("approval", approval)
    graph.add_node("finish", finish)
    graph.add_edge(START, "begin")
    graph.add_edge("begin", "approval")
    graph.add_edge("approval", "finish")
    graph.add_edge("finish", END)
    app = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "approval-thread"}}
    first = await app.ainvoke({"value": 0, "approved": False}, config=config)
    interrupted = "__interrupt__" in first
    second = await app.ainvoke(Command(resume=True), config=config)
    return {"interrupted": interrupted, "final_value": second["value"]}


async def run(iterations: int = 30) -> dict[str, Any]:
    current_diamond = [await _current_diamond_once() for _ in range(iterations)]
    current_values = [value for value, _ in current_diamond]
    current_latencies = [latency for _, latency in current_diamond]
    result: dict[str, Any] = {
        "iterations": iterations,
        "current_runtime": {
            "diamond_result": current_values[0],
            "diamond_consistent": len(set(current_values)) == 1,
            "p50_ms": _percentile(current_latencies, 0.5),
            "p95_ms": _percentile(current_latencies, 0.95),
        },
        "langgraph_available": LANGGRAPH_AVAILABLE,
        "langgraph_version": LANGGRAPH_VERSION,
    }
    if not LANGGRAPH_AVAILABLE:
        return result

    app = _langgraph_diamond_app()
    lg_diamond = [await _langgraph_diamond_once(app) for _ in range(iterations)]
    lg_values = [value for value, _ in lg_diamond]
    lg_latencies = [latency for _, latency in lg_diamond]
    current_retry = await _current_retry_once()
    lg_retry = await _langgraph_retry_once()
    current_resume = await _current_checkpoint_resume()
    lg_interrupt = await _langgraph_interrupt_resume()
    result["langgraph"] = {
        "diamond_result": lg_values[0],
        "diamond_consistent": len(set(lg_values)) == 1,
        "p50_ms": _percentile(lg_latencies, 0.5),
        "p95_ms": _percentile(lg_latencies, 0.95),
        "retry_result": lg_retry,
        "interrupt_resume": lg_interrupt,
    }
    result["comparison"] = {
        "diamond_result_match": current_values[0] == lg_values[0],
        "current_retry": current_retry,
        "langgraph_retry": lg_retry,
        "current_checkpoint_resume": current_resume,
        "current_has_native_interrupt": False,
        "langgraph_has_native_interrupt": lg_interrupt["interrupted"],
        "current_has_native_cycle": False,
        "langgraph_has_native_cycle": True,
        "current_has_streaming": False,
        "langgraph_has_streaming": hasattr(app, "astream"),
    }
    return result


def main() -> None:
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
