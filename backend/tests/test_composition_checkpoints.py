from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.composition_checkpoint import CompositionExecutionCheckpoint
from app.schemas.composition import CompositionEdge, CompositionNode, CompositionPlan
from app.services.composition_checkpoint_store import (
    load_checkpoint_sync,
    save_checkpoint_sync,
)
from app.services.async_dag_runtime import AsyncDagRuntime


def _engine():
    from tests.test_semantic_registry_seed import _engine as registry_engine

    engine = registry_engine()
    Base.metadata.create_all(engine, tables=[CompositionExecutionCheckpoint.__table__])
    return engine


def test_checkpoint_save_load_roundtrip():
    engine = _engine()
    save_checkpoint_sync(
        engine,
        execution_id="exec-1",
        plan_id="plan-1",
        registry_version="v1",
        state={"completed_order": ["a"], "node_results": {"a": {"value": 1}}},
    )
    loaded = load_checkpoint_sync(engine, "exec-1")
    assert loaded is not None
    assert loaded["node_results"]["a"]["value"] == 1
    assert loaded["completed_order"] == ["a"]


@pytest.mark.asyncio
async def test_runtime_resumes_from_checkpoint():
    calls: list[str] = []

    async def source(_inputs):
        calls.append("source")
        return {"value": 1}

    async def target(inputs):
        calls.append("target")
        return {"value": inputs["value"] + 1}

    plan = CompositionPlan(
        plan_id="p1",
        nodes=[
            CompositionNode(node_id="a", module_id="a"),
            CompositionNode(node_id="b", module_id="b"),
        ],
        edges=[CompositionEdge(from_node="a", from_output="value", to_node="b", to_input="value")],
    )
    checkpoint = {
        "node_results": {"a": {"value": 1}},
        "completed_order": ["a"],
        "failed_nodes": [],
        "skipped_nodes": [],
        "total_cost": 0.0,
    }
    saved = {}

    async def load(_execution_id):
        return checkpoint

    async def save(execution_id, state):
        saved[execution_id] = state

    result = await AsyncDagRuntime().execute(
        plan,
        handlers={"a": source, "b": target},
        execution_id="exec-1",
        checkpoint_load=load,
        checkpoint_save=save,
    )
    assert calls == ["target"]
    assert result.node_results["b"]["value"] == 2
    assert saved["exec-1"]["completed_order"] == ["a", "b"]
