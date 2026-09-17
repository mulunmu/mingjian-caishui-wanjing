from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest


def test_langgraph_dependency_is_isolated():
    root = Path(__file__).resolve().parents[1]
    core = (root / "requirements.txt").read_text(encoding="utf-8").lower()
    optional = (root / "requirements-orchestration.txt").read_text(
        encoding="utf-8"
    ).lower()
    core_lock = (root / "requirements.lock.txt").read_text(
        encoding="utf-8"
    ).lower()
    optional_lock = (root / "requirements-orchestration.lock.txt").read_text(
        encoding="utf-8"
    ).lower()
    assert "langgraph" not in core
    assert "langgraph" not in core_lock
    assert "langgraph" in optional
    assert "langgraph" in optional_lock


@pytest.mark.asyncio
async def test_disabled_outer_orchestrator_uses_primary_path(monkeypatch):
    from app.services import outer_orchestrator, semantic_primary

    called = {}

    async def primary(**kwargs):
        called.update(kwargs)
        return {"reply": "primary", "session_id": kwargs["session_id"], "data": {}}

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "false")
    monkeypatch.setattr(semantic_primary, "run_primary_turn", primary)
    out = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id="outer-disabled",
        owner=None,
        query="你好",
    )
    assert out["reply"] == "primary"
    assert called["query"] == "你好"


@pytest.mark.asyncio
async def test_enabled_orchestrator_requires_dependency_for_approval(monkeypatch):
    from app.services import outer_orchestrator

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "true")
    monkeypatch.setattr(outer_orchestrator, "langgraph_available", lambda: False)
    with pytest.raises(RuntimeError, match="not installed"):
        await outer_orchestrator.run_outer_turn(
            db=object(),
            session_id="outer-missing",
            owner=None,
            query="生成报告",
            approval=True,
        )


@pytest.mark.asyncio
async def test_langgraph_parity_and_report_interrupt_resume(monkeypatch):
    pytest.importorskip("langgraph")
    from app.services import outer_orchestrator, semantic_primary

    async def primary(**kwargs):
        return {
            "reply": "报告已生成",
            "session_id": kwargs["session_id"],
            "data": {
                "primary": {"status": "answered", "fallback": False, "route": "report"},
                "claims": [{"metric": "report", "value": "ok"}],
            },
        }

    async def classify(self, query):
        del self, query
        return {
            "route": "report",
            "domain": "report",
            "language": "zh",
            "entities": [],
            "needs_tools": False,
            "needs_clarification": False,
            "confidence": 0.99,
        }

    monkeypatch.setattr(semantic_primary, "run_primary_turn", primary)
    monkeypatch.setattr(outer_orchestrator.OuterTurnRuntime, "classify", classify)

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "false")
    direct = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id="outer-parity",
        owner=None,
        query="生成报告",
    )

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "true")
    parity = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id="outer-parity",
        owner=None,
        query="生成报告",
        require_approval=False,
    )
    assert parity["reply"] == direct["reply"]
    assert parity["data"]["claims"] == direct["data"]["claims"]

    session_id = "outer-approval"
    pending = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="生成报告",
        require_approval=True,
    )
    assert pending["data"]["primary"]["approval_required"] is True
    assert pending["data"]["primary"]["orchestrator"]["status"] == "approval_required"
    assert [
        item["agent"]
        for item in pending["data"]["primary"]["orchestrator"]["agents"]
    ] == ["memory_agent", "classification_agent", "planning_agent"]

    resumed = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="确认生成报告",
        require_approval=True,
    )
    assert resumed["reply"] == "报告已生成"
    assert resumed["data"]["primary"]["orchestrator"]["status"] == "completed"
    agents = resumed["data"]["primary"]["orchestrator"]["agents"]
    assert [item["agent"] for item in agents] == [
        "memory_agent",
        "classification_agent",
        "planning_agent",
        "approval_agent",
        "execution_agent",
        "verification_agent",
    ]


@pytest.mark.asyncio
async def test_langgraph_memory_agent_traces_topic_context(monkeypatch):
    pytest.importorskip("langgraph")
    from app.services import outer_orchestrator, semantic_primary

    async def primary(**kwargs):
        return {
            "reply": "memory answer",
            "session_id": kwargs["session_id"],
            "data": {"primary": {"status": "answered", "fallback": False}},
        }

    async def classify(self, query):
        del self, query
        return {"route": "analysis", "domain": "tax"}

    async def load_memory(self, query):
        del self, query
        return {"topic_count": 12, "recent_topic_ids": ["topic-1", "topic-2"]}

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "true")
    monkeypatch.setattr(semantic_primary, "run_primary_turn", primary)
    monkeypatch.setattr(outer_orchestrator.OuterTurnRuntime, "classify", classify)
    monkeypatch.setattr(outer_orchestrator.OuterTurnRuntime, "load_memory", load_memory)

    out = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id="outer-memory-agent",
        owner=None,
        query="那个税负的事继续分析",
        require_approval=False,
    )
    agents = out["data"]["primary"]["orchestrator"]["agents"]
    memory_trace = next(item for item in agents if item["agent"] == "memory_agent")
    assert memory_trace["reference_detected"] is True
    assert memory_trace["topic_count"] == 12


@pytest.mark.asyncio
async def test_stale_report_approval_does_not_hijack_unrelated_question(monkeypatch):
    pytest.importorskip("langgraph")
    from app.services import outer_orchestrator, semantic_primary

    async def primary(**kwargs):
        return {
            "reply": "无关问题正常回答",
            "session_id": kwargs["session_id"],
            "data": {"primary": {"status": "answered", "fallback": False}},
        }

    async def classify(self, query):
        del self
        route = "report" if "报告" in query else "greeting"
        return {"route": route, "domain": route}

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "true")
    monkeypatch.setattr(semantic_primary, "run_primary_turn", primary)
    monkeypatch.setattr(outer_orchestrator.OuterTurnRuntime, "classify", classify)

    session_id = f"outer-stale-{uuid.uuid4().hex}"
    first = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="生成报告",
        require_approval=True,
    )
    assert first["data"]["primary"]["approval_required"] is True

    second = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="你好，继续聊别的",
        require_approval=True,
    )
    assert second["reply"] == "无关问题正常回答"


@pytest.mark.asyncio
async def test_langgraph_report_cancel_does_not_execute(monkeypatch):
    pytest.importorskip("langgraph")
    from app.services import outer_orchestrator, semantic_primary

    executed = False

    async def primary(**kwargs):
        nonlocal executed
        del kwargs
        executed = True
        return {"reply": "unexpected", "data": {}}

    async def classify(self, query):
        del self, query
        return {"route": "report", "domain": "report"}

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "true")
    monkeypatch.setattr(semantic_primary, "run_primary_turn", primary)
    monkeypatch.setattr(outer_orchestrator.OuterTurnRuntime, "classify", classify)

    session_id = "outer-cancel"
    await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="生成报告",
        require_approval=True,
    )
    cancelled = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="取消生成报告",
        require_approval=True,
    )
    assert executed is False
    assert cancelled["data"]["primary"]["orchestrator"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_postgres_checkpointer_resumes_with_new_saver_instance(monkeypatch):
    pytest.importorskip("langgraph.checkpoint.postgres")
    if not os.getenv("LANGGRAPH_CHECKPOINT_DATABASE_URL"):
        pytest.skip("LANGGRAPH_CHECKPOINT_DATABASE_URL not configured")
    from app.services import outer_orchestrator, semantic_primary

    async def primary(**kwargs):
        return {
            "reply": "durable resume",
            "session_id": kwargs["session_id"],
            "data": {"primary": {"status": "answered", "fallback": False}},
        }

    async def classify(self, query):
        del self, query
        return {"route": "report", "domain": "report"}

    monkeypatch.setenv("LANGGRAPH_OUTER_ENABLED", "true")
    monkeypatch.setattr(semantic_primary, "run_primary_turn", primary)
    monkeypatch.setattr(outer_orchestrator.OuterTurnRuntime, "classify", classify)

    session_id = f"outer-durable-{uuid.uuid4().hex}"
    pending = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="生成报告",
        require_approval=True,
    )
    assert pending["data"]["primary"]["approval_required"] is True
    resumed = await outer_orchestrator.run_outer_turn(
        db=object(),
        session_id=session_id,
        owner=None,
        query="确认生成报告",
        approval=True,
        require_approval=True,
    )
    assert resumed["reply"] == "durable resume"
    assert resumed["data"]["primary"]["orchestrator"]["status"] == "completed"
