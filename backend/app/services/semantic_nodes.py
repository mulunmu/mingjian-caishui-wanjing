"""LLM-first semantic planning nodes used by the outer LangGraph."""
from __future__ import annotations

import logging
from typing import Any, Callable

from app.schemas.semantic_plan import SemanticPlan
from app.services import llm_reply
from app.services.composition_catalog import build_composition_catalog
from app.services.semantic_frame import frame_from_route
from app.services.semantic_planner import (
    semantic_legacy_route_fallback_enabled,
    semantic_planner_langgraph_node_enabled,
    semantic_planner_selected,
    semantic_report_plan_enabled,
    plan_semantic_turn,
    semantic_plan_to_composition_plan,
    semantic_planner_enabled,
    validate_semantic_plan,
)
from app.services.semantic_tool_executors import semantic_executor_tool_ids


logger = logging.getLogger(__name__)


async def _default_snapshot_loader(db):
    from app.services.tool_rag import load_tool_snapshot

    return await load_tool_snapshot(db)


async def _default_inventory_loader(db, top_n: int = 1):
    from app.services import inventory_scope

    return await inventory_scope.load_inventory(db, top_n=top_n)


def _allowed_filter_values(inventory: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "industry_l1": {
            str(item.get("industry_l1")).strip()
            for item in inventory.get("industries") or []
            if item.get("industry_l1")
        },
        "province": {
            str(item.get("province")).strip()
            for item in inventory.get("provinces") or []
            if item.get("province") and item.get("province") != "未标注"
        },
        "city": {
            str(item.get("city")).strip()
            for item in inventory.get("cities") or []
            if item.get("city")
        },
    }


def _plan_eligible(route, raw_route: dict[str, Any]) -> bool:
    dialog_act = raw_route.get("dialog_act") if isinstance(raw_route, dict) else None
    refusal_kind = (dialog_act or {}).get("refusal_kind") if isinstance(dialog_act, dict) else None
    if refusal_kind == "fabrication" or route.route == "abuse":
        return False
    return route.route not in {"abuse", "unknown_entity", "language_switch"}


def _candidate_tool_ids(plan: SemanticPlan | None) -> list[str]:
    if plan is None:
        return []
    return [step.tool_id for step in plan.steps]


async def semantic_planner_node(
    *,
    db,
    session_id: str | None = None,
    query: str,
    raw_route: dict[str, Any],
    memory_context: dict[str, Any] | None = None,
    snapshot_loader: Callable | None = None,
    inventory_loader: Callable | None = None,
    catalog_builder: Callable | None = None,
) -> dict[str, Any]:
    """Produce a SemanticPlan without executing tools."""
    planner_available = (
        semantic_planner_langgraph_node_enabled()
        and semantic_planner_enabled()
        and semantic_planner_selected(session_id)
        and llm_reply.llm_available()
    )
    if not planner_available:
        if not semantic_legacy_route_fallback_enabled():
            return {
                "planner_status": "clarify",
                "planner_attempts": 0,
                "planner_errors": [
                    "semantic_planner_unavailable_without_legacy_route_fallback"
                ],
                "planner_clarification": "语义规划服务暂不可用，请稍后重试或换一种更具体的问法。",
                "semantic_plan": None,
                "composition_plan": None,
                "semantic_candidate_tool_ids": [],
            }
        return {
            "planner_status": "disabled_or_unavailable",
            "planner_attempts": 0,
            "planner_errors": [],
            "planner_clarification": None,
            "semantic_plan": None,
            "composition_plan": None,
            "semantic_candidate_tool_ids": [],
        }

    from app.services.route_normalize import normalize_route

    route = normalize_route(raw_route, query)
    frame = frame_from_route(route, query=query)
    if not _plan_eligible(route, raw_route):
        return {
            "planner_status": "skipped",
            "planner_attempts": 0,
            "planner_errors": [],
            "planner_clarification": None,
            "semantic_plan": None,
            "composition_plan": None,
            "semantic_candidate_tool_ids": [],
        }

    load_snapshot = snapshot_loader or _default_snapshot_loader
    load_inventory = inventory_loader or _default_inventory_loader
    build_catalog = catalog_builder or build_composition_catalog
    try:
        snapshot = await load_snapshot(db)
        catalog = build_catalog(snapshot)
        inventory = await load_inventory(db, top_n=1)
        dialogue_state = (
            (memory_context or {}).get("dialogue_state")
            if isinstance(memory_context, dict)
            else None
        ) or {}
        active_analysis = bool(
            dialogue_state.get("analysis_focus")
            and dialogue_state.get("scope") in {"individual", "cohort"}
        )
        result = await plan_semantic_turn(
            query=query,
            route=route,
            candidate_tools=[],
            executable_tool_ids=semantic_executor_tool_ids(),
            modules=catalog,
            allowed_filter_values=_allowed_filter_values(inventory),
            session_context={
                "memory": memory_context or {},
                "raw_route": raw_route,
                "dialogue_state": dialogue_state,
                "analysis_continuation_required": active_analysis,
            },
        )
        if (
            active_analysis
            and result.status == "ok"
            and result.plan is not None
            and result.plan.action.value != "analysis"
        ):
            retry = await plan_semantic_turn(
                query=query,
                route=route,
                candidate_tools=[],
                executable_tool_ids=semantic_executor_tool_ids(),
                modules=catalog,
                allowed_filter_values=_allowed_filter_values(inventory),
                session_context={
                    "memory": memory_context or {},
                    "raw_route": raw_route,
                    "dialogue_state": dialogue_state,
                    "analysis_continuation_required": True,
                    "continuation_retry": True,
                },
                max_attempts=1,
            )
            if retry.status == "ok" and retry.plan is not None:
                result = retry
    except Exception as exc:
        logger.warning("semantic planner node failed closed: %s", exc)
        return {
            "planner_status": "clarify",
            "planner_attempts": 0,
            "planner_errors": [str(exc)],
            "planner_clarification": "暂时无法确认分析目标，请补充企业、行业或地区和具体指标。",
            "semantic_plan": None,
            "composition_plan": None,
            "semantic_candidate_tool_ids": [],
        }

    if result.status == "ok" and result.plan is not None:
        return {
            "planner_status": "ok",
            "planner_attempts": result.attempts,
            "planner_errors": list(result.errors),
            "planner_clarification": None,
            "semantic_plan": result.plan.model_dump(mode="json"),
            "composition_plan": (
                result.composition_plan.model_dump(mode="json")
                if result.composition_plan is not None
                else None
            ),
            "semantic_candidate_tool_ids": _candidate_tool_ids(result.plan),
        }
    return {
        "planner_status": result.status,
        "planner_attempts": result.attempts,
        "planner_errors": list(result.errors),
        "planner_clarification": result.clarification_question,
        "semantic_plan": None,
        "composition_plan": None,
        "semantic_candidate_tool_ids": [],
    }


async def capability_retrieval_node(
    *,
    db,
    semantic_plan: dict[str, Any] | None,
    snapshot_loader: Callable | None = None,
    inventory_loader: Callable | None = None,
    catalog_builder: Callable | None = None,
) -> dict[str, Any]:
    """Check whether the semantic plan references live capabilities and values."""
    if not semantic_plan:
        return {"capability_status": "skipped", "capability_errors": []}
    try:
        plan = SemanticPlan.model_validate(semantic_plan)
        snapshot = await (snapshot_loader or _default_snapshot_loader)(db)
        inventory = await (inventory_loader or _default_inventory_loader)(db, top_n=1)
        catalog = (catalog_builder or build_composition_catalog)(snapshot)
        report = validate_semantic_plan(
            plan,
            executable_tool_ids=semantic_executor_tool_ids(),
            modules=catalog,
            allowed_filter_values=_allowed_filter_values(inventory),
        )
    except Exception as exc:
        return {
            "capability_status": "invalid",
            "capability_errors": [str(exc)],
            "semantic_candidate_tool_ids": [],
        }
    return {
        "capability_status": "valid" if report.valid else "invalid",
        "capability_errors": [error.message for error in report.errors],
        "semantic_candidate_tool_ids": _candidate_tool_ids(plan),
    }


async def plan_validator_node(
    *,
    db,
    semantic_plan: dict[str, Any] | None,
    snapshot_loader: Callable | None = None,
    inventory_loader: Callable | None = None,
    catalog_builder: Callable | None = None,
) -> dict[str, Any]:
    """Validate the plan and materialize the executable composition DAG."""
    if not semantic_plan:
        return {"planner_status": "skipped", "composition_plan": None}
    try:
        plan = SemanticPlan.model_validate(semantic_plan)
        snapshot = await (snapshot_loader or _default_snapshot_loader)(db)
        inventory = await (inventory_loader or _default_inventory_loader)(db, top_n=1)
        catalog = (catalog_builder or build_composition_catalog)(snapshot)
        executable_tool_ids = semantic_executor_tool_ids()
        allowed_filter_values = _allowed_filter_values(inventory)
        if plan.action != "analysis":
            report = validate_semantic_plan(
                plan,
                executable_tool_ids=executable_tool_ids,
                modules=catalog,
                allowed_filter_values=allowed_filter_values,
            )
            if report.valid:
                return {
                    "planner_status": "ok",
                    "planner_errors": [],
                    "planner_clarification": None,
                    "semantic_plan": plan.model_dump(mode="json"),
                    "composition_plan": None,
                    "semantic_candidate_tool_ids": [],
                }
        validated, composition = semantic_plan_to_composition_plan(
            plan,
            modules=catalog,
            executable_tool_ids=executable_tool_ids,
            allowed_filter_values=allowed_filter_values,
        )
        if validated is None or composition is None:
            report = validate_semantic_plan(
                plan,
                executable_tool_ids=executable_tool_ids,
                modules=catalog,
                allowed_filter_values=allowed_filter_values,
            )
            return {
                "planner_status": "clarify",
                "planner_errors": [error.message for error in report.errors],
                "planner_clarification": plan.clarification_question
                or "分析方案暂时无法执行，请补充指标或缩小分析范围。",
                "composition_plan": None,
            }
    except Exception as exc:
        logger.warning("semantic plan validator failed closed: %s", exc)
        return {
            "planner_status": "clarify",
            "planner_errors": [str(exc)],
            "planner_clarification": "分析方案暂时无法校验，请换一种更具体的问法。",
            "composition_plan": None,
        }
    return {
        "planner_status": "ok",
        "planner_errors": [],
        "planner_clarification": None,
        "semantic_plan": validated.model_dump(mode="json"),
        "composition_plan": composition.model_dump(mode="json"),
        "semantic_candidate_tool_ids": _candidate_tool_ids(validated),
    }


def _normalize_filter_aliases(plan: SemanticPlan) -> SemanticPlan:
    from app.services.semantic_lexicon import _match_industry, _match_province

    def normalize(values: dict[str, list[str]]) -> dict[str, list[str]]:
        output: dict[str, list[str]] = {}
        for key, items in (values or {}).items():
            normalized: list[str] = []
            for item in items:
                value = str(item).strip()
                if key == "industry_l1":
                    value = _match_industry(value) or value
                elif key == "province":
                    value = _match_province(value) or value
                if value and value not in normalized:
                    normalized.append(value)
            if normalized:
                output[key] = normalized
        return output

    steps = [
        step.model_copy(update={"filters": normalize(step.filters)})
        for step in plan.steps
    ]
    return plan.model_copy(
        update={
            "filters": normalize(plan.filters),
            "steps": steps,
        }
    )


async def plan_repair_node(
    *,
    db,
    semantic_plan: dict[str, Any] | None,
    planner_errors: list[str] | None = None,
    snapshot_loader: Callable | None = None,
    inventory_loader: Callable | None = None,
    catalog_builder: Callable | None = None,
) -> dict[str, Any]:
    """Repair deterministic alias/format issues, then fail closed if unsafe."""
    if not semantic_plan or not planner_errors:
        return {"repair_status": "not_needed"}
    try:
        plan = _normalize_filter_aliases(SemanticPlan.model_validate(semantic_plan))
        snapshot = await (snapshot_loader or _default_snapshot_loader)(db)
        inventory = await (inventory_loader or _default_inventory_loader)(db, top_n=1)
        catalog = (catalog_builder or build_composition_catalog)(snapshot)
        validated, composition = semantic_plan_to_composition_plan(
            plan,
            modules=catalog,
            executable_tool_ids=semantic_executor_tool_ids(),
            allowed_filter_values=_allowed_filter_values(inventory),
        )
    except Exception as exc:
        return {
            "repair_status": "needs_user_input",
            "planner_status": "clarify",
            "planner_errors": [str(exc)],
            "composition_plan": None,
        }
    if validated is None or composition is None:
        return {
            "repair_status": "needs_user_input",
            "planner_status": "clarify",
            "planner_errors": list(planner_errors),
            "planner_clarification": "无法自动修复分析方案，请补充更明确的指标、行业或地区。",
            "composition_plan": None,
        }
    return {
        "repair_status": "repaired",
        "planner_status": "ok",
        "planner_errors": [],
        "planner_clarification": None,
        "semantic_plan": validated.model_dump(mode="json"),
        "composition_plan": composition.model_dump(mode="json"),
        "semantic_candidate_tool_ids": _candidate_tool_ids(validated),
    }


def evidence_critic_node(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result or {})
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    primary = data.get("primary") if isinstance(data.get("primary"), dict) else {}
    claims = data.get("claims") if isinstance(data.get("claims"), list) else []
    issues: list[str] = []
    if not str(payload.get("reply") or "").strip():
        issues.append("empty_reply")
    if primary.get("fallback") is not False:
        issues.append("fallback_response")
    if primary.get("route") == "analysis" and not claims:
        issues.append("analysis_without_claims")
    for index, claim in enumerate(claims):
        trace = claim.get("trace") if isinstance(claim, dict) else None
        if not trace or not trace.get("table") or not trace.get("field"):
            issues.append(f"untraceable_claim:{index}")
    status = "failed" if issues else "completed"
    primary["evidence_critic"] = {"status": status, "issues": issues}
    payload["data"] = {**data, "primary": primary}
    return {
        "result": payload,
        "evidence_critic_status": status,
        "evidence_critic_issues": issues,
    }


def report_planner_node(result: dict[str, Any]) -> dict[str, Any]:
    """Mark report planning intent; full ReportPlan is added in Task 10."""
    if not semantic_report_plan_enabled():
        return {"result": dict(result or {}), "report_plan_status": "disabled"}
    payload = dict(result or {})
    primary = (
        (payload.get("data") or {}).get("primary")
        if isinstance(payload.get("data"), dict)
        else {}
    ) or {}
    if primary.get("route") != "report":
        return {"result": payload, "report_plan_status": "not_requested"}
    return {"result": payload, "report_plan_status": "deferred"}


def response_composer_node(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result or {})
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    primary = data.get("primary") if isinstance(data.get("primary"), dict) else {}
    primary["response_composer"] = {"status": "completed"}
    payload["data"] = {**data, "primary": primary}
    return {"result": payload, "response_composer_status": "completed"}
