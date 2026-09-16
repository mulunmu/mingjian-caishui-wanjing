"""Optional LangGraph outer state machine around the deterministic primary path."""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, TypedDict

from app.db.urls import sync_database_url
from app.services import session_store
from app.services.dialog_act import classify as classify_dialog_act
from app.services.shadow_integration import dialog_act_to_raw_route
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)

_CHECKPOINTER = None
_CHECKPOINT_SETUP_LOCK = asyncio.Lock()
_CHECKPOINT_SETUP_DSNS: set[str] = set()


class OuterTurnState(TypedDict, total=False):
    query: str
    approval: bool | None
    approval_required: bool
    raw_route: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class OuterTurnRuntime:
    db: Any
    session_id: str
    owner: str | None
    enterprise_id: str | None
    user: dict | None

    async def classify(self, query: str) -> dict[str, Any]:
        session_context = await run_blocking(session_store.get_session, self.session_id)
        act = await classify_dialog_act(query, session_context or {})
        raw_route = dialog_act_to_raw_route(act, query)
        if self.enterprise_id:
            entities = list(raw_route.get("entities") or [])
            if self.enterprise_id not in entities:
                entities.insert(0, self.enterprise_id)
            raw_route = {**raw_route, "entities": entities}
        return raw_route

    async def execute(self, query: str, raw_route: dict[str, Any]) -> dict[str, Any]:
        from app.services.semantic_primary import run_primary_turn

        return await run_primary_turn(
            db=self.db,
            session_id=self.session_id,
            owner=self.owner,
            query=query,
            raw_route=raw_route,
            enterprise_id=self.enterprise_id,
            user=self.user,
        )


def outer_orchestrator_enabled() -> bool:
    return os.getenv("LANGGRAPH_OUTER_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def report_approval_required() -> bool:
    return os.getenv("LANGGRAPH_REPORT_APPROVAL_REQUIRED", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def langgraph_available() -> bool:
    return importlib.util.find_spec("langgraph") is not None


def _approval_from_query(query: str) -> bool | None:
    normalized = (query or "").strip().lower()
    if any(token in normalized for token in ("取消", "不生成", "算了", "否", "不要")):
        return False
    if any(token in normalized for token in ("确认", "同意", "可以", "生成", "是")):
        return True
    return None


def _get_checkpointer():
    global _CHECKPOINTER
    if _CHECKPOINTER is None:
        from langgraph.checkpoint.memory import InMemorySaver

        _CHECKPOINTER = InMemorySaver()
    return _CHECKPOINTER


@asynccontextmanager
async def _checkpointer_context():
    dsn = os.getenv("LANGGRAPH_CHECKPOINT_DATABASE_URL") or sync_database_url()
    if not dsn:
        yield _get_checkpointer()
        return
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        if dsn not in _CHECKPOINT_SETUP_DSNS:
            async with _CHECKPOINT_SETUP_LOCK:
                if dsn not in _CHECKPOINT_SETUP_DSNS:
                    await saver.setup()
                    _CHECKPOINT_SETUP_DSNS.add(dsn)
        yield saver


def _pending_response(runtime: OuterTurnRuntime) -> dict[str, Any]:
    return {
        "reply": "报告生成需要确认。确认后将执行报告流程。",
        "reply_source": "langgraph_interrupt",
        "analysis_mode": "rule",
        "parse_source": "langgraph_outer",
        "intent": "report",
        "function": "report",
        "dimension": "report",
        "session_id": runtime.session_id,
        "followups": ["确认生成报告", "取消生成报告"],
        "followup_items": [
            {"type": "query", "label": "确认生成报告", "params": {"query": "确认生成报告"}},
            {"type": "query", "label": "取消生成报告", "params": {"query": "取消生成报告"}},
        ],
        "data": {
            "primary": {
                "status": "clarify",
                "fallback": False,
                "route": "report",
                "approval_required": True,
                "orchestrator": {
                    "engine": "langgraph",
                    "status": "approval_required",
                    "session_id": runtime.session_id,
                },
            },
            "claims": [],
        },
    }


def _cancelled_response(runtime: OuterTurnRuntime) -> dict[str, Any]:
    return {
        "reply": "已取消报告生成。",
        "reply_source": "langgraph_interrupt",
        "analysis_mode": "rule",
        "parse_source": "langgraph_outer",
        "intent": "report",
        "function": "report",
        "dimension": "report",
        "session_id": runtime.session_id,
        "followups": ["继续分析", "重新选择报告"],
        "data": {
            "primary": {
                "status": "answered",
                "fallback": False,
                "route": "report",
                "orchestrator": {
                    "engine": "langgraph",
                    "status": "cancelled",
                    "session_id": runtime.session_id,
                },
            },
            "claims": [],
        },
    }


def _compile_graph(runtime: OuterTurnRuntime, *, require_approval: bool):
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    async def classify_node(state: OuterTurnState) -> OuterTurnState:
        raw_route = await runtime.classify(state["query"])
        return {
            "raw_route": raw_route,
            "approval_required": bool(
                require_approval and raw_route.get("route") == "report"
            ),
        }

    async def approval_node(state: OuterTurnState) -> OuterTurnState:
        approval = state.get("approval")
        if approval is None:
            approval = interrupt(
                {
                    "kind": "report_confirmation",
                    "session_id": runtime.session_id,
                    "message": "确认生成报告？",
                }
            )
        return {"approval": bool(approval)}

    async def execute_node(state: OuterTurnState) -> OuterTurnState:
        result = await runtime.execute(state["query"], state["raw_route"])
        return {"result": result}

    async def cancel_node(_: OuterTurnState) -> OuterTurnState:
        return {"result": _cancelled_response(runtime)}

    async def review_node(state: OuterTurnState) -> OuterTurnState:
        result = dict(state.get("result") or {})
        primary = result.setdefault("data", {}).setdefault("primary", {})
        if primary.get("fallback"):
            raise RuntimeError("outer orchestrator rejected fallback primary response")
        primary["orchestrator"] = {
            "engine": "langgraph",
            "status": "completed",
            "session_id": runtime.session_id,
        }
        return {"result": result}

    def after_classify(state: OuterTurnState) -> str:
        return "approval" if state.get("approval_required") else "execute"

    def after_approval(state: OuterTurnState) -> str:
        return "execute" if state.get("approval") else "cancel"

    graph = StateGraph(OuterTurnState)
    graph.add_node("classify", classify_node)
    graph.add_node("approval", approval_node)
    graph.add_node("execute", execute_node)
    graph.add_node("cancel", cancel_node)
    graph.add_node("review", review_node)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        after_classify,
        {"approval": "approval", "execute": "execute"},
    )
    graph.add_conditional_edges(
        "approval",
        after_approval,
        {"execute": "execute", "cancel": "cancel"},
    )
    graph.add_edge("execute", "review")
    graph.add_edge("review", END)
    graph.add_edge("cancel", END)
    return graph, Command


async def _run_langgraph(
    runtime: OuterTurnRuntime,
    *,
    query: str,
    approval: bool | None,
    require_approval: bool,
) -> dict[str, Any]:
    graph, Command = _compile_graph(runtime, require_approval=require_approval)
    async with _checkpointer_context() as checkpointer:
        app = graph.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": runtime.session_id}}
        snapshot = await app.aget_state(config)
        pending = bool(snapshot.next)
        effective_approval = approval
        if pending and effective_approval is None:
            effective_approval = _approval_from_query(query)
        if pending and effective_approval is None:
            return _pending_response(runtime)
        if pending:
            raw = await app.ainvoke(Command(resume=effective_approval), config=config)
        else:
            raw = await app.ainvoke(
                {
                    "query": query,
                    "approval": effective_approval,
                    "approval_required": False,
                    "raw_route": {},
                    "result": {},
                },
                config=config,
            )
    if isinstance(raw, dict) and "__interrupt__" in raw:
        return _pending_response(runtime)
    result = (raw or {}).get("result") if isinstance(raw, dict) else None
    return result if isinstance(result, dict) else _pending_response(runtime)


async def run_outer_turn(
    *,
    db,
    session_id: str,
    owner: str | None,
    query: str,
    enterprise_id: str | None = None,
    user: dict | None = None,
    approval: bool | None = None,
    require_approval: bool | None = None,
) -> dict[str, Any]:
    """Run the optional outer graph, falling back to the primary path when disabled."""
    runtime = OuterTurnRuntime(
        db=db,
        session_id=session_id,
        owner=owner,
        enterprise_id=enterprise_id,
        user=user,
    )
    effective_require_approval = (
        report_approval_required() if require_approval is None else require_approval
    )
    if not outer_orchestrator_enabled():
        from app.services.semantic_primary import run_primary_turn

        return await run_primary_turn(
            db=db,
            session_id=session_id,
            owner=owner,
            query=query,
            enterprise_id=enterprise_id,
            user=user,
        )
    if not langgraph_available():
        logger.warning("LangGraph outer orchestrator enabled but dependency is missing")
        if approval is not None or effective_require_approval:
            raise RuntimeError("LangGraph outer orchestrator dependency is not installed")
        from app.services.semantic_primary import run_primary_turn

        return await run_primary_turn(
            db=db,
            session_id=session_id,
            owner=owner,
            query=query,
            enterprise_id=enterprise_id,
            user=user,
        )
    return await _run_langgraph(
        runtime,
        query=query,
        approval=approval,
        require_approval=effective_require_approval,
    )
