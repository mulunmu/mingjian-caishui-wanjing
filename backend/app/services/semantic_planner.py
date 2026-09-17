"""LLM planning with deterministic validation and DAG materialization.

The LLM is responsible for semantic intent and proposing a combination. It is
not allowed to invent tools, metrics, filters or numbers. The validator is the
only authority that turns a proposal into an executable composition plan.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from app.schemas.composition import (
    CompositionEdge,
    CompositionNode,
    CompositionPlan,
    ModuleSpec,
)
from app.schemas.conversation_route import ConversationRoute
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.semantic_plan import (
    SemanticPlan,
    SemanticPlanStep,
    SemanticPlanValidationError,
    SemanticPlanValidationReport,
)
from app.services import llm_reply
from app.services.semantic_frame_from_plan import frame_from_plan
from app.services.analysis_patterns import ANALYSIS_PATTERNS, COMPARISON_BASIS
from app.services.composition_validator import validate_composition_plan


logger = logging.getLogger(__name__)

PlanningStatus = Literal["ok", "clarify", "unavailable"]

_ALLOWED_FILTER_KEYS = {
    "industry_l1",
    "province",
    "city",
}
_MAX_ANALYSIS_STEPS = 6
_COMPARISON_BASIS_ALIASES = {
    "industry": "cohort_slice",
    "industry_l1": "cohort_slice",
    "province": "cohort_slice",
    "region": "cohort_slice",
    "group": "cohort_slice",
    "slice": "cohort_slice",
    "peer_industry": "peer",
    "same_industry": "peer",
}


def semantic_planner_enabled() -> bool:
    return os.getenv("SEMANTIC_PLANNER_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }


@dataclass
class SemanticPlanningResult:
    status: PlanningStatus
    plan: SemanticPlan | None = None
    composition_plan: CompositionPlan | None = None
    attempts: int = 0
    clarification_question: str | None = None
    errors: list[str] = field(default_factory=list)


def _issue(code: str, message: str, step_id: str | None = None):
    return SemanticPlanValidationError(
        code=code,
        message=message,
        step_id=step_id,
    )


def _filter_values(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _validate_filter_map(
    filters: dict[str, list[str]],
    *,
    allowed_filter_values: dict[str, set[str]] | None,
    step_id: str | None = None,
) -> list[SemanticPlanValidationError]:
    errors: list[SemanticPlanValidationError] = []
    for key, values in (filters or {}).items():
        if key not in _ALLOWED_FILTER_KEYS:
            errors.append(_issue("filter_not_allowed", f"unsupported filter: {key}", step_id))
            continue
        allowed = (allowed_filter_values or {}).get(key)
        if allowed is None:
            continue
        for value in _filter_values(values):
            if value not in allowed:
                errors.append(
                    _issue(
                        "filter_value_not_found",
                        f"{key}={value} is not present in the data inventory",
                        step_id,
                    )
                )
    return errors


def _has_cycle(steps: list[SemanticPlanStep]) -> bool:
    dependencies = {step.step_id: set(step.depends_on or []) for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for parent in dependencies.get(node, set()):
            if parent not in dependencies or visit(parent):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in dependencies)


def validate_semantic_plan(
    plan: SemanticPlan,
    *,
    executable_tool_ids: set[str] | None,
    modules: dict[str, ModuleSpec],
    allowed_filter_values: dict[str, set[str]] | None = None,
) -> SemanticPlanValidationReport:
    errors: list[SemanticPlanValidationError] = []
    executable_tool_ids = set(executable_tool_ids or set(modules))
    steps = list(plan.steps or [])

    if plan.action == "analysis":
        if not steps:
            if not plan.metrics:
                errors.append(_issue("missing_steps", "analysis plan has no executable steps"))
            else:
                steps = [
                    SemanticPlanStep(
                        step_id=f"metric_{index}",
                        tool_id=f"metric_{metric}",
                    )
                    for index, metric in enumerate(plan.metrics, start=1)
                ]
        if plan.confidence < 0.55:
            errors.append(_issue("low_confidence", "planner confidence is below the execution threshold"))
        if plan.ambiguous:
            errors.append(
                _issue(
                    "ambiguous_plan",
                    plan.clarification_question or "the planner marked the request as ambiguous",
                )
            )
        if len(steps) > _MAX_ANALYSIS_STEPS:
            errors.append(_issue("plan_too_large", f"analysis plan exceeds {_MAX_ANALYSIS_STEPS} steps"))

    step_ids = [step.step_id for step in steps]
    if len(set(step_ids)) != len(step_ids):
        errors.append(_issue("duplicate_step_id", "step IDs must be unique"))

    for step in steps:
        if step.tool_id not in executable_tool_ids:
            errors.append(
                _issue(
                    "tool_not_executable",
                    f"tool is not executable: {step.tool_id}",
                    step.step_id,
                )
            )
        module = modules.get(step.tool_id)
        if module is None:
            errors.append(_issue("module_not_found", f"module not found: {step.tool_id}", step.step_id))
        elif module.status != "validated":
            errors.append(
                _issue(
                    "module_not_executable",
                    f"module is not validated: {step.tool_id}",
                    step.step_id,
                )
            )
        errors.extend(
            _validate_filter_map(
                step.filters,
                allowed_filter_values=allowed_filter_values,
                step_id=step.step_id,
            )
        )
        for parent in step.depends_on or []:
            if parent not in step_ids:
                errors.append(
                    _issue(
                        "dependency_not_found",
                        f"step dependency not found: {parent}",
                        step.step_id,
                    )
                )

    if _has_cycle(steps):
        errors.append(_issue("plan_cycle", "analysis plan contains a cycle"))

    for metric in plan.metrics:
        tool_id = f"metric_{metric}"
        if tool_id not in executable_tool_ids:
            errors.append(_issue("metric_not_executable", f"metric is not executable: {metric}"))

    step_metric_keys = [
        step.tool_id.removeprefix("metric_")
        for step in steps
        if step.tool_id.startswith("metric_")
    ]
    extra_metrics = [metric for metric in plan.metrics if metric not in step_metric_keys]
    warnings = [
        _issue(
            "metric_not_in_steps",
            f"metric is not bound to an executable step and will be ignored: {metric}",
        )
        for metric in extra_metrics
    ]

    for pattern in plan.analysis_patterns:
        if pattern not in ANALYSIS_PATTERNS:
            errors.append(_issue("analysis_pattern_not_found", f"unsupported analysis pattern: {pattern}"))
    if plan.comparison_basis and plan.comparison_basis not in COMPARISON_BASIS:
        errors.append(
            _issue(
                "comparison_basis_not_found",
                f"unsupported comparison basis: {plan.comparison_basis}",
            )
        )

    errors.extend(
        _validate_filter_map(
            plan.filters,
            allowed_filter_values=allowed_filter_values,
        )
    )

    return SemanticPlanValidationReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        metadata={
            "step_count": len(steps),
            "tool_ids": [step.tool_id for step in steps],
            "analysis_patterns": list(plan.analysis_patterns),
        },
    )


def _plan_steps(plan: SemanticPlan) -> list[SemanticPlanStep]:
    if plan.steps:
        return list(plan.steps)
    return [
        SemanticPlanStep(
            step_id=f"metric_{index}",
            tool_id=f"metric_{metric}",
        )
        for index, metric in enumerate(plan.metrics, start=1)
    ]


def _merged_filters(plan: SemanticPlan, step: SemanticPlanStep) -> dict[str, Any]:
    merged: dict[str, list[str]] = {
        key: list(values) for key, values in (plan.filters or {}).items()
    }
    for key, values in (step.filters or {}).items():
        merged[key] = list(values)
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in merged.items()
        if values
    }


def _dependency_edge(
    source: SemanticPlanStep,
    target: SemanticPlanStep,
    modules: dict[str, ModuleSpec],
) -> CompositionEdge | None:
    source_module = modules.get(source.tool_id)
    target_module = modules.get(target.tool_id)
    if source_module is None or target_module is None:
        return None
    source_outputs = {port.name for port in source_module.outputs}
    target_inputs = {port.name for port in target_module.inputs}
    for port_name in ("claims", "value", "series", "text"):
        if port_name in source_outputs and port_name in target_inputs:
            return CompositionEdge(
                from_node=source.step_id,
                from_output=port_name,
                to_node=target.step_id,
                to_input=port_name,
            )
    return None


def semantic_plan_to_composition_plan(
    plan: SemanticPlan,
    *,
    modules: dict[str, ModuleSpec],
    executable_tool_ids: set[str] | None = None,
    allowed_filter_values: dict[str, set[str]] | None = None,
) -> tuple[SemanticPlan | None, CompositionPlan | None]:
    if plan.action != "analysis" or not _plan_steps(plan):
        return None, None
    report = validate_semantic_plan(
        plan,
        executable_tool_ids=executable_tool_ids,
        modules=modules,
        allowed_filter_values=allowed_filter_values,
    )
    if not report.valid:
        return None, None

    steps = _plan_steps(plan)
    step_metrics = [
        step.tool_id.removeprefix("metric_")
        for step in steps
        if step.tool_id.startswith("metric_")
    ]
    if step_metrics:
        plan = plan.model_copy(update={"metrics": step_metrics})
    nodes: list[CompositionNode] = []
    edges: list[CompositionEdge] = []
    for step in steps:
        bindings: dict[str, Any] = {
            "query": plan.plan_summary or " ".join(plan.metrics),
            **_merged_filters(plan, step),
        }
        entity = step.entity or (plan.entities[0] if plan.entities else None)
        if entity:
            bindings["entity"] = entity
        if step.dimension:
            bindings["dimension"] = step.dimension
        nodes.append(
            CompositionNode(
                node_id=step.step_id,
                module_id=step.tool_id,
                input_bindings=bindings,
                cost_estimate=modules[step.tool_id].cost,
            )
        )

    for step in steps:
        for parent_id in step.depends_on or []:
            parent = next((item for item in steps if item.step_id == parent_id), None)
            if parent is None:
                return None, None
            edge = _dependency_edge(parent, step, modules)
            if edge is None:
                return None, None
            edges.append(edge)

    composition = CompositionPlan(
        plan_id="plan-semantic-" + "-".join(step.tool_id for step in steps)[:120],
        nodes=nodes,
        edges=edges,
        output_node_ids=[node.node_id for node in nodes],
        metadata={
            "semantic_plan": True,
            "strategy": "llm_semantic_plan",
            "selected_tool_ids": [step.tool_id for step in steps],
            "analysis_patterns": list(plan.analysis_patterns),
            "comparison_basis": plan.comparison_basis,
            "plan_summary": plan.plan_summary,
        },
    )
    composition_report = validate_composition_plan(composition, modules)
    if not composition_report.valid:
        return None, None
    return plan, composition


def semantic_plan_to_frame(
    plan: SemanticPlan,
    *,
    route: ConversationRoute,
    base: SemanticFrame,
) -> SemanticFrame:
    return frame_from_plan(plan, route=route, base=base)


def _tool_rows(
    candidate_tools: list[Any],
    modules: dict[str, ModuleSpec],
    executable_tool_ids: set[str] | None = None,
) -> list[dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for item in candidate_tools or []:
        if isinstance(item, dict):
            tool_id = str(item.get("tool_id") or "")
            title = str(item.get("title") or "")
            description = str(item.get("description") or "")
        else:
            tool_id = str(getattr(item, "tool_id", "") or "")
            title = str(getattr(item, "title", "") or "")
            description = str(getattr(item, "description", "") or "")
        if tool_id and (executable_tool_ids is None or tool_id in executable_tool_ids):
            rows[tool_id] = {
                "tool_id": tool_id,
                "title": title,
                "description": description,
            }
    for tool_id, module in modules.items():
        if module.kind != "metric" or module.status != "validated":
            continue
        if executable_tool_ids is not None and tool_id not in executable_tool_ids:
            continue
        rows.setdefault(
            tool_id,
            {
                "tool_id": tool_id,
                "title": str(module.metadata.get("title") or tool_id),
                "description": "",
            },
        )
    return [rows[key] for key in sorted(rows)]


def _planner_system_prompt(
    *,
    route: ConversationRoute,
    candidate_tools: list[Any],
    modules: dict[str, ModuleSpec],
    executable_tool_ids: set[str] | None,
    allowed_filter_values: dict[str, set[str]] | None,
    session_context: dict[str, Any] | None,
    repair_errors: list[str] | None = None,
) -> str:
    tool_rows = _tool_rows(candidate_tools, modules, executable_tool_ids)
    tool_text = "\n".join(
        f"- {row['tool_id']} | {row['title']} | {row['description'][:120]}"
        for row in tool_rows
    )
    patterns = ", ".join(sorted(ANALYSIS_PATTERNS))
    comparison_bases = ", ".join(sorted(COMPARISON_BASIS))
    filter_text = "; ".join(
        f"{key}={sorted(values)[:40]}"
        for key, values in sorted((allowed_filter_values or {}).items())
    ) or "无"
    context = json.dumps(session_context or {}, ensure_ascii=False)[:1200]
    continuation_hint = ""
    if (session_context or {}).get("analysis_continuation_required"):
        continuation_hint = (
            "当前处于已有分析会话的延续轮次。除非用户明确问候、拒绝或切换到其他话题，"
            "否则 action 必须是 analysis，并继承会话中的 analysis_focus、实体和 filters。\n"
        )
    repair = ""
    if repair_errors:
        repair = "上一版计划未通过校验，必须修复这些问题：\n- " + "\n- ".join(repair_errors) + "\n"
    return (
        "你是财税风控系统的语义执行规划器。只输出 JSON，不要输出思考过程、Markdown 或解释。\n"
        "你的任务是理解用户真正想做什么，并从给出的真实工具目录中提出可执行组合。\n"
        "工具目录：\n"
        f"{tool_text}\n"
        f"可用分析模式：{patterns}\n"
        f"可用对比基准：{comparison_bases}\n"
        f"可用筛选值（只能使用真实值）：{filter_text}\n"
        f"粗路由：{route.route}；domain={route.domain or 'general'}。\n"
        f"会话上下文：{context}\n"
        f"{continuation_hint}"
        "硬规则：\n"
        "1. tool_id、metric、分析模式和筛选值只能来自目录/真实值；不得发明。\n"
        "2. 分析类 action=analysis，必须给出 1 到 6 个 steps；可选 metric 工具和 operator 工具。\n"
        "3. 需要对比多个对象时，用多个 step，各自绑定真实 filters；不要只选一个指标后假装完成了组合。\n"
        "4. metrics 填 step 对应的 metric_key，不带 metric_ 前缀。analysis_patterns 使用上面的英文键。\n"
        "4a. operator step 必须通过 depends_on 指向已有 step；组合关系只能是目录中真实存在的端口。\n"
        "4b. comparison_basis 只能使用上面的对比基准英文键；按行业/地区分组对比用 cohort_slice，同行对比用 peer。\n"
        "5. 若目录无法支撑用户要求，设置 ambiguous=true 并在 clarification_question 给出一个具体澄清问题，不要猜。\n"
        "6. 数字、阈值、企业名单和结论绝不能由你生成；它们只会由执行器返回的 Claim 提供。\n"
        "7. plan_summary 只写一句面向用户的任务摘要，不写隐藏推理。\n"
        "8. action 只能是 analysis/metadata_query/profile/report/conversation/clarify/refuse；当前阶段只执行 analysis 的工具组合。\n"
        f"{repair}"
        "输出字段：action, route_hint, planner_version, policy_tags, scope, entities, resolved_references, "
        "filters, metrics, analysis_patterns, comparison_basis, steps, output_requirements, confidence, "
        "ambiguous, ambiguity_reason, clarification_question, requires_confirmation, report_plan, "
        "plan_summary, planner_notes, repair_history。"
    )


def _planner_user_prompt(query: str, repair_errors: list[str] | None = None) -> str:
    suffix = ""
    if repair_errors:
        suffix = "\n请根据校验错误重新规划，只返回修复后的 JSON。"
    return f"用户原话：{query}{suffix}"


def _normalize_plan(plan: SemanticPlan) -> SemanticPlan:
    updates: dict[str, Any] = {}
    basis = str(plan.comparison_basis or "").strip().lower()
    if basis in _COMPARISON_BASIS_ALIASES:
        updates["comparison_basis"] = _COMPARISON_BASIS_ALIASES[basis]
    if updates:
        return plan.model_copy(update=updates)
    return plan


async def _default_completion(system: str, user: str, response_model):
    try:
        return await llm_reply._async_instructor_completion(
            system,
            user,
            response_model,
            max_tokens=1800,
            temperature=0.0,
            max_retries=0,
        )
    except Exception as first_error:
        logger.info("instructor planner failed, trying JSON fallback: %s", first_error)
        return await llm_reply._async_json_completion(
            system,
            user,
            response_model,
            max_tokens=1800,
            temperature=0.0,
        )


async def plan_semantic_turn(
    query: str,
    *,
    route: ConversationRoute,
    candidate_tools: list[Any],
    executable_tool_ids: set[str],
    modules: dict[str, ModuleSpec],
    allowed_filter_values: dict[str, set[str]] | None = None,
    session_context: dict[str, Any] | None = None,
    completion_fn: Callable[..., Awaitable[Any]] | None = None,
    max_attempts: int = 2,
) -> SemanticPlanningResult:
    if completion_fn is None and not llm_reply.llm_available():
        return SemanticPlanningResult(status="unavailable", attempts=0)

    completion = completion_fn or _default_completion
    attempts = max(1, min(3, int(max_attempts or 1)))
    errors: list[str] = []
    last_plan: SemanticPlan | None = None
    for attempt in range(1, attempts + 1):
        system = _planner_system_prompt(
            route=route,
            candidate_tools=candidate_tools,
            modules=modules,
            executable_tool_ids=executable_tool_ids,
            allowed_filter_values=allowed_filter_values,
            session_context=session_context,
            repair_errors=errors or None,
        )
        try:
            raw = await completion(system, _planner_user_prompt(query, errors or None), SemanticPlan)
        except Exception as exc:
            logger.warning("semantic planner completion failed: %s", exc)
            errors = [f"planner_error: {exc}"]
            continue
        try:
            plan = raw if isinstance(raw, SemanticPlan) else SemanticPlan.model_validate(raw)
            plan = _normalize_plan(plan)
        except Exception as exc:
            errors = [f"schema_error: {exc}"]
            continue
        last_plan = plan
        report = validate_semantic_plan(
            plan,
            executable_tool_ids=executable_tool_ids,
            modules=modules,
            allowed_filter_values=allowed_filter_values,
        )
        if report.valid:
            if plan.action != "analysis":
                return SemanticPlanningResult(
                    status="ok",
                    plan=plan,
                    composition_plan=None,
                    attempts=attempt,
                )
            validated_plan, composition = semantic_plan_to_composition_plan(
                plan,
                modules=modules,
                executable_tool_ids=executable_tool_ids,
                allowed_filter_values=allowed_filter_values,
            )
            if validated_plan is not None and composition is not None:
                return SemanticPlanningResult(
                    status="ok",
                    plan=validated_plan,
                    composition_plan=composition,
                    attempts=attempt,
                )
        errors = [error.message for error in report.errors]

    return SemanticPlanningResult(
        status="clarify",
        attempts=attempts,
        clarification_question=(
            (last_plan.clarification_question if last_plan else None)
            or "我还不能确定要组合哪些指标。请说明分析对象、行业或地区，以及想比较或查看的指标。"
        ),
        errors=errors,
    )
