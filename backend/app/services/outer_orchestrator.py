"""Optional LangGraph outer state machine around the deterministic primary path."""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypedDict

from app.db.urls import sync_database_url
from app.db.urls import get_sync_engine
from app.services import semantic_nodes, session_store
from app.services.dialog_act import classify as classify_dialog_act
from app.services.shadow_integration import dialog_act_to_raw_route
from app.services.sync_runner import run_blocking
from app.services.progress import emit_progress
from app.services.observability import get_trace_id, increment_metric, observe_latency
from app.services.topic_memory import (
    compose_memory_context_blocking,
    looks_like_topic_reference,
)

logger = logging.getLogger(__name__)

_CHECKPOINTER = None
_CHECKPOINT_SETUP_LOCK = asyncio.Lock()
_CHECKPOINT_SETUP_DSNS: set[str] = set()


class OuterTurnState(TypedDict, total=False):
    query: str
    approval: bool | None
    approval_requested_at: str
    approval_required: bool
    memory_context: dict[str, Any]
    agent_trace: list[dict[str, Any]]
    execution_started_at: float
    raw_route: dict[str, Any]
    semantic_plan: dict[str, Any] | None
    composition_plan: dict[str, Any] | None
    planner_status: str
    planner_attempts: int
    planner_errors: list[str]
    planner_clarification: str | None
    semantic_candidate_tool_ids: list[str]
    capability_status: str
    capability_errors: list[str]
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
        if getattr(act, "act", None) == "custom_report":
            raw_route["custom_report"] = True
        if self.enterprise_id:
            entities = list(raw_route.get("entities") or [])
            if self.enterprise_id not in entities:
                entities.insert(0, self.enterprise_id)
            raw_route = {**raw_route, "entities": entities}
        return raw_route

    async def load_memory(self, query: str) -> dict[str, Any]:
        if not looks_like_topic_reference(query):
            return {}
        try:
            return await run_blocking(
                compose_memory_context_blocking,
                get_sync_engine(),
                self.session_id,
                query=query,
            )
        except Exception as exc:
            logger.warning("outer memory agent unavailable: %s", exc)
            return {}

    async def execute(
        self,
        query: str,
        raw_route: dict[str, Any],
        *,
        memory_context: dict[str, Any] | None = None,
        semantic_plan: dict[str, Any] | None = None,
        composition_plan: dict[str, Any] | None = None,
        planner_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from app.services.semantic_primary import run_primary_turn

        return await run_primary_turn(
            db=self.db,
            session_id=self.session_id,
            owner=self.owner,
            query=query,
            raw_route=raw_route,
            enterprise_id=self.enterprise_id,
            user=self.user,
            memory_context=memory_context,
            semantic_plan=semantic_plan,
            composition_plan=composition_plan,
            planner_meta=planner_meta,
        )


def outer_orchestrator_enabled() -> bool:
    return os.getenv("LANGGRAPH_OUTER_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }


def report_approval_required() -> bool:
    return os.getenv("LANGGRAPH_REPORT_APPROVAL_REQUIRED", "true").lower() in {
        "1",
        "true",
        "yes",
    }


def approval_ttl_seconds() -> int:
    try:
        return max(1, int(os.getenv("LANGGRAPH_APPROVAL_TTL_SECONDS", "900")))
    except ValueError:
        return 900


def finance_review_enabled() -> bool:
    return os.getenv("LANGGRAPH_FINANCE_REVIEW_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
    }


def final_guard_enabled() -> bool:
    return os.getenv("LANGGRAPH_FINAL_GUARD_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }


def agent_budget_ms() -> int:
    try:
        return max(1000, int(os.getenv("LANGGRAPH_AGENT_BUDGET_MS", "15000")))
    except ValueError:
        return 15000


def _final_guard_issues(result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    reply = str(result.get("reply") or "").strip()
    primary = ((result.get("data") or {}).get("primary") or {}) if isinstance(result, dict) else {}
    if not reply:
        issues.append("empty_reply")
    if primary.get("fallback") is not False:
        issues.append("fallback_response")
    claims = (result.get("data") or {}).get("claims") or []
    for index, claim in enumerate(claims):
        trace = claim.get("trace") if isinstance(claim, dict) else None
        if not trace or not trace.get("table") or not trace.get("field"):
            issues.append(f"untraceable_claim:{index}")
    return issues


def _approval_expired(values: dict[str, Any]) -> bool:
    raw = str(values.get("approval_requested_at") or "").strip()
    if not raw:
        return False
    try:
        requested = datetime.fromisoformat(raw)
        if requested.tzinfo is None:
            requested = requested.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - requested).total_seconds() > approval_ttl_seconds()


def _approval_expires_at(values: dict[str, Any]) -> str | None:
    raw = str(values.get("approval_requested_at") or "").strip()
    if not raw:
        return None
    try:
        requested = datetime.fromisoformat(raw)
        if requested.tzinfo is None:
            requested = requested.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    expires = requested.timestamp() + approval_ttl_seconds()
    return datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()


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


def _pending_response(
    runtime: OuterTurnRuntime,
    agents: list[dict[str, Any]] | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
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
                    "agents": list(agents or []),
                    "approval_expires_at": expires_at,
                },
            },
            "claims": [],
        },
    }


def _expired_response(runtime: OuterTurnRuntime) -> dict[str, Any]:
    return {
        "reply": "报告确认已过期，请重新发起报告生成。",
        "reply_source": "langgraph_interrupt",
        "analysis_mode": "rule",
        "parse_source": "langgraph_outer",
        "intent": "report",
        "function": "report",
        "dimension": "report",
        "session_id": runtime.session_id,
        "followups": ["重新生成报告", "继续分析"],
        "data": {
            "primary": {
                "status": "clarify",
                "fallback": False,
                "route": "report",
                "approval_expired": True,
                "orchestrator": {
                    "engine": "langgraph",
                    "status": "approval_expired",
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


def _semantic_clarification_response(
    runtime: OuterTurnRuntime,
    state: OuterTurnState,
) -> dict[str, Any]:
    question = str(state.get("planner_clarification") or "").strip() or (
        "我还不能确定分析目标。请补充企业、行业或地区，以及想查看的指标。"
    )
    return {
        "reply": question,
        "reply_source": "semantic_planner",
        "analysis_mode": "llm",
        "parse_source": "semantic_langgraph",
        "intent": "clarify",
        "function": "general",
        "dimension": "overall",
        "session_id": runtime.session_id,
        "followups": [],
        "data": {
            "primary": {
                "status": "clarify",
                "fallback": False,
                "route": "clarify",
                "semantic_planner_status": "clarify",
                "semantic_planner_attempts": state.get("planner_attempts") or 0,
                "semantic_planner_errors": list(state.get("planner_errors") or []),
                "semantic_plan": state.get("semantic_plan"),
                "semantic_candidate_tool_ids": list(
                    state.get("semantic_candidate_tool_ids") or []
                ),
            },
            "claims": [],
        },
    }


def _compile_graph(runtime: OuterTurnRuntime, *, require_approval: bool):
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command, interrupt

    def append_trace(
        state: OuterTurnState,
        agent: str,
        status: str,
        **details: Any,
    ) -> list[dict[str, Any]]:
        trace = list(state.get("agent_trace") or [])
        trace.append(
            {
                "agent": agent,
                "status": status,
                "trace_id": get_trace_id(),
                **details,
            }
        )
        return trace

    def finish_agent(agent: str, started: float) -> None:
        increment_metric("agent_runs_total", {"agent": agent, "status": "completed"})
        observe_latency(
            "agent_latency_ms",
            (time.perf_counter() - started) * 1000,
            {"agent": agent},
        )

    async def memory_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        await emit_progress("memory", "正在读取会话上下文", "恢复实体、话题和最近结论")
        memory_context = await runtime.load_memory(state["query"])
        finish_agent("memory_agent", started)
        return {
            "memory_context": memory_context,
            "agent_trace": append_trace(
                state,
                "memory_agent",
                "completed",
                reference_detected=bool(memory_context),
                topic_count=memory_context.get("topic_count", 0),
            ),
        }

    async def classify_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        await emit_progress("intent", "正在识别问题意图", "判断这是知识、分析、报告还是其他会话")
        raw_route = await runtime.classify(state["query"])
        finish_agent("classification_agent", started)
        return {
            "raw_route": raw_route,
            "agent_trace": append_trace(
                state,
                "classification_agent",
                "completed",
                route=raw_route.get("route"),
            ),
        }

    async def semantic_planner_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        await emit_progress("planning", "正在理解语义并规划工具", "LLM 负责方案，系统负责边界")
        payload = await semantic_nodes.semantic_planner_node(
            db=runtime.db,
            query=state["query"],
            raw_route=state.get("raw_route") or {},
            memory_context=state.get("memory_context") or {},
        )
        finish_agent("semantic_planner_agent", started)
        return {
            **payload,
            "agent_trace": append_trace(
                state,
                "semantic_planner_agent",
                payload.get("planner_status") or "skipped",
                tool_count=len(payload.get("semantic_candidate_tool_ids") or []),
            ),
        }

    async def capability_retrieval_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        payload = await semantic_nodes.capability_retrieval_node(
            db=runtime.db,
            semantic_plan=state.get("semantic_plan"),
        )
        finish_agent("capability_retrieval_agent", started)
        return {
            **payload,
            "agent_trace": append_trace(
                state,
                "capability_retrieval_agent",
                payload.get("capability_status") or "skipped",
            ),
        }

    async def plan_validator_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        payload = await semantic_nodes.plan_validator_node(
            db=runtime.db,
            semantic_plan=state.get("semantic_plan"),
        )
        finish_agent("plan_validator_agent", started)
        return {
            **payload,
            "agent_trace": append_trace(
                state,
                "plan_validator_agent",
                payload.get("planner_status") or "skipped",
            ),
        }

    async def planning_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        await emit_progress("planning", "正在制定执行路径", "校验范围、工具和审批要求")
        raw_route = state.get("raw_route") or {}
        approval_required = bool(
            require_approval
            and raw_route.get("route") == "report"
            and not raw_route.get("custom_report")
        )
        finish_agent("planning_agent", started)
        return {
            "approval_required": approval_required,
            "agent_trace": append_trace(
                state,
                "planning_agent",
                "completed",
                approval_required=approval_required,
                memory_topics=len(
                    (state.get("memory_context") or {}).get("recent_topic_ids") or []
                ),
            ),
        }

    async def approval_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        approval = state.get("approval")
        if approval is None:
            approval = interrupt(
                {
                    "kind": "report_confirmation",
                    "session_id": runtime.session_id,
                    "message": "确认生成报告？",
                }
            )
        finish_agent("approval_agent", started)
        return {
            "approval": bool(approval),
            "agent_trace": append_trace(
                state,
                "approval_agent",
                "completed",
                approved=bool(approval),
            ),
        }

    async def execute_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        await emit_progress("execution", "正在执行分析", "调用确定性工具并生成可追溯结论")
        if state.get("planner_status") == "clarify":
            result = _semantic_clarification_response(runtime, state)
        else:
            result = await runtime.execute(
                state["query"],
                state["raw_route"],
                memory_context=state.get("memory_context") or {},
                semantic_plan=state.get("semantic_plan"),
                composition_plan=state.get("composition_plan"),
                planner_meta={
                    "status": state.get("planner_status"),
                    "attempts": state.get("planner_attempts") or 0,
                    "errors": list(state.get("planner_errors") or []),
                },
            )
        finish_agent("execution_agent", started)
        return {
            "result": result,
            "execution_started_at": started,
            "agent_trace": append_trace(
                state,
                "execution_agent",
                "completed",
            ),
        }

    async def finance_review_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        if finance_review_enabled():
            await emit_progress("finance_review", "正在进行金融语义复核")
        result = dict(state.get("result") or {})
        primary = result.setdefault("data", {}).setdefault("primary", {})
        status = "skipped"
        reason = "disabled"
        interpretation = None
        if finance_review_enabled():
            from app.schemas.claim import Claim
            from app.services import llm_reply

            raw_claims = (result.get("data") or {}).get("claims") or []
            claims = [Claim.model_validate(item) for item in raw_claims]
            if not claims:
                reason = "no_claims"
            elif not llm_reply.financial_llm_available():
                reason = "financial_model_unavailable"
            else:
                try:
                    interpretation = await llm_reply.generate_financial_interpretation(
                        claims,
                        {
                            "industry_l1": primary.get("industry_l1"),
                            "scope": primary.get("scope"),
                            "scenario": primary.get("domain"),
                        },
                    )
                    status = "completed" if interpretation else "skipped"
                    reason = None if interpretation else "empty_interpretation"
                except Exception as exc:
                    status = "failed"
                    reason = str(exc)
        if interpretation:
            primary["finance_review"] = {"status": status, "interpretation": interpretation}
        finish_agent(f"finance_review_agent:{status}", started)
        return {
            "result": result,
            "agent_trace": append_trace(
                state,
                "finance_review_agent",
                status,
                reason=reason,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
        }

    async def final_guard_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        await emit_progress("guard", "正在校验回答", "核对数字、企业、阈值和事实边界")
        result = dict(state.get("result") or {})
        issues = _final_guard_issues(result) if final_guard_enabled() else []
        budget_ms = agent_budget_ms()
        turn_started = float(state.get("execution_started_at") or time.perf_counter())
        elapsed_ms = (time.perf_counter() - turn_started) * 1000
        if final_guard_enabled() and elapsed_ms > budget_ms:
            issues.append("agent_budget_exceeded")
        status = "failed" if issues else "completed"
        finish_agent(f"final_guard_agent:{status}", started)
        if issues:
            raise RuntimeError(f"final guard rejected response: {issues}")
        primary = result.setdefault("data", {}).setdefault("primary", {})
        primary["final_guard"] = {
            "status": status,
            "budget_ms": budget_ms,
            "elapsed_ms": round(elapsed_ms, 2),
        }
        return {
            "result": result,
            "agent_trace": append_trace(
                state,
                "final_guard_agent",
                status,
                budget_ms=budget_ms,
                elapsed_ms=round(elapsed_ms, 2),
            ),
        }

    async def cancel_node(_: OuterTurnState) -> OuterTurnState:
        return {"result": _cancelled_response(runtime)}

    async def review_node(state: OuterTurnState) -> OuterTurnState:
        started = time.perf_counter()
        result = dict(state.get("result") or {})
        primary = result.setdefault("data", {}).setdefault("primary", {})
        if primary.get("fallback"):
            raise RuntimeError("outer orchestrator rejected fallback primary response")
        trace = append_trace(
            state,
            "verification_agent",
            "completed",
            fallback=bool(primary.get("fallback")),
        )
        primary["orchestrator"] = {
            "engine": "langgraph",
            "status": "completed",
            "session_id": runtime.session_id,
            "agents": trace,
        }
        finish_agent("verification_agent", started)
        return {
            "result": result,
            "agent_trace": trace,
        }

    def after_planning(state: OuterTurnState) -> str:
        return "approval" if state.get("approval_required") else "execute"

    def after_approval(state: OuterTurnState) -> str:
        return "execute" if state.get("approval") else "cancel"

    graph = StateGraph(OuterTurnState)
    graph.add_node("memory", memory_node)
    graph.add_node("classify", classify_node)
    graph.add_node("semantic_planner", semantic_planner_node)
    graph.add_node("capability_retrieval", capability_retrieval_node)
    graph.add_node("plan_validator", plan_validator_node)
    graph.add_node("planning", planning_node)
    graph.add_node("approval", approval_node)
    graph.add_node("execute", execute_node)
    graph.add_node("finance_review", finance_review_node)
    graph.add_node("final_guard", final_guard_node)
    graph.add_node("cancel", cancel_node)
    graph.add_node("review", review_node)
    graph.add_edge(START, "memory")
    graph.add_edge("memory", "classify")
    graph.add_edge("classify", "semantic_planner")
    graph.add_edge("semantic_planner", "capability_retrieval")
    graph.add_edge("capability_retrieval", "plan_validator")
    graph.add_edge("plan_validator", "planning")
    graph.add_conditional_edges(
        "planning",
        after_planning,
        {"approval": "approval", "execute": "execute"},
    )
    graph.add_conditional_edges(
        "approval",
        after_approval,
        {"execute": "execute", "cancel": "cancel"},
    )
    graph.add_edge("execute", "finance_review")
    graph.add_edge("finance_review", "final_guard")
    graph.add_edge("final_guard", "review")
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
        state_values = getattr(snapshot, "values", None) or {}
        effective_approval = approval
        if pending and effective_approval is None:
            effective_approval = _approval_from_query(query)
        if pending and effective_approval is None:
            # A stale report interrupt must not hijack an unrelated new question.
            # Start a fresh thread and leave the old interrupt abandoned.
            config = {
                "configurable": {
                    "thread_id": f"{runtime.session_id}:detour:{uuid.uuid4().hex}"
                }
            }
            pending = False
        if pending and effective_approval is not None and _approval_expired(state_values):
            return _expired_response(runtime)
        if pending:
            raw = await app.ainvoke(Command(resume=effective_approval), config=config)
        else:
            approval_requested_at = datetime.now(timezone.utc).isoformat()
            raw = await app.ainvoke(
                {
                    "query": query,
                    "approval": effective_approval,
                    "approval_requested_at": approval_requested_at,
                    "approval_required": False,
                    "memory_context": {},
                    "agent_trace": [],
                    "raw_route": {},
                    "result": {},
                },
                config=config,
            )
    if isinstance(raw, dict) and "__interrupt__" in raw:
        return _pending_response(
            runtime,
            raw.get("agent_trace"),
            _approval_expires_at(raw),
        )
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
