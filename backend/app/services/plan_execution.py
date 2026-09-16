"""Validation and deterministic execution for typed tool plans."""
from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from typing import Any

from app.schemas.conversation_route import ConversationPolicy
from app.schemas.tool_plan import ToolPlan, ToolPlanExecution
from app.services.tool_rag import ToolSnapshot


class PlanValidationError(ValueError):
    pass


def _tool_map(snapshot: ToolSnapshot):
    return {tool.tool_id: tool for tool in snapshot.tools}


def _topological_order(plan: ToolPlan) -> list[str]:
    steps = {step.step_id: step for step in plan.steps}
    visiting: set[str] = set()
    visited: set[str] = set()
    ordered: list[str] = []

    def visit(step_id: str) -> None:
        if step_id in visiting:
            raise PlanValidationError("cycle detected")
        if step_id in visited:
            return
        visiting.add(step_id)
        for dependency in steps[step_id].depends_on:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)
        ordered.append(step_id)

    for step_id in steps:
        visit(step_id)
    return ordered


def validate_tool_plan(
    plan: ToolPlan,
    snapshot: ToolSnapshot,
    *,
    policy: ConversationPolicy | None = None,
) -> list[str]:
    if policy is not None and plan.steps and not policy.execute_tools:
        raise PlanValidationError("conversation policy does not allow tool execution")

    step_ids = [step.step_id for step in plan.steps]
    if len(step_ids) != len(set(step_ids)):
        raise PlanValidationError("duplicate step_id")

    tools = _tool_map(snapshot)
    by_step = {step.step_id: step for step in plan.steps}
    available_tool_ids = {step.tool_id for step in plan.steps}

    for step in plan.steps:
        tool = tools.get(step.tool_id)
        if tool is None:
            raise PlanValidationError(f"unknown tool: {step.tool_id}")
        missing = set(tool.required_params) - set(step.params)
        if missing:
            raise PlanValidationError(
                f"missing params for {step.tool_id}: {sorted(missing)}"
            )
        for dependency in step.depends_on:
            if dependency not in by_step:
                raise PlanValidationError(f"missing dependency: {dependency}")
        for required_tool_id in tool.dependencies:
            if required_tool_id == step.tool_id:
                continue
            if required_tool_id not in available_tool_ids:
                raise PlanValidationError(
                    f"missing required tool {required_tool_id} for {step.tool_id}"
                )
            dependency_step_ids = {
                dependency_id
                for dependency_id in step.depends_on
                if by_step[dependency_id].tool_id == required_tool_id
            }
            if not dependency_step_ids:
                raise PlanValidationError(
                    f"{step.tool_id} must depend on {required_tool_id}"
                )

    return _topological_order(plan)


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return {"value": value}


def execute_tool_plan(
    plan: ToolPlan,
    snapshot: ToolSnapshot,
    tool_fns: dict[str, Callable[..., dict[str, Any]]],
    *,
    policy: ConversationPolicy | None = None,
) -> ToolPlanExecution:
    ordered = validate_tool_plan(plan, snapshot, policy=policy)
    by_step = {step.step_id: step for step in plan.steps}
    step_outputs: dict[str, dict[str, Any]] = {}
    claims: list[dict[str, Any]] = []

    for step_id in ordered:
        step = by_step[step_id]
        fn = tool_fns.get(step.tool_id)
        if fn is None:
            raise PlanValidationError(f"no executor registered for {step.tool_id}")
        dependency_outputs = {
            dependency_id: step_outputs[dependency_id]
            for dependency_id in step.depends_on
        }
        raw = fn(params=dict(step.params), dependency_results=dependency_outputs)
        output = _json_dict(raw)
        step_outputs[step_id] = output
        output_claims = output.get("claims")
        if isinstance(output_claims, list):
            claims.extend(_json_dict(claim) for claim in output_claims)
        elif output:
            claims.append(output)

    return ToolPlanExecution(
        plan=plan,
        claims=claims,
        step_outputs=step_outputs,
    )


async def execute_tool_plan_async(
    plan: ToolPlan,
    snapshot: ToolSnapshot,
    tool_fns: dict[str, Callable[..., Any]],
    *,
    policy: ConversationPolicy | None = None,
) -> ToolPlanExecution:
    ordered = validate_tool_plan(plan, snapshot, policy=policy)
    by_step = {step.step_id: step for step in plan.steps}
    step_outputs: dict[str, dict[str, Any]] = {}
    claims: list[dict[str, Any]] = []

    for step_id in ordered:
        step = by_step[step_id]
        fn = tool_fns.get(step.tool_id)
        if fn is None:
            raise PlanValidationError(f"no executor registered for {step.tool_id}")
        dependency_outputs = {
            dependency_id: step_outputs[dependency_id]
            for dependency_id in step.depends_on
        }
        raw = fn(params=dict(step.params), dependency_results=dependency_outputs)
        if inspect.isawaitable(raw):
            raw = await raw
        output = _json_dict(raw)
        step_outputs[step_id] = output
        output_claims = output.get("claims")
        if isinstance(output_claims, list):
            claims.extend(_json_dict(claim) for claim in output_claims)
        elif output:
            claims.append(output)

    return ToolPlanExecution(
        plan=plan,
        claims=claims,
        step_outputs=step_outputs,
    )