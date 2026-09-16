"""Deterministic planner that materializes reusable composition patterns."""
from __future__ import annotations

from typing import Any

from app.schemas.composition import (
    CompositionEdge,
    CompositionNode,
    CompositionPlan,
    ModuleSpec,
)
from app.services.composition_patterns import PATTERNS, PatternRole
from app.services.composition_validator import validate_composition_plan


def _select_module(
    role: PatternRole,
    candidates: list[str],
    modules: dict[str, ModuleSpec],
) -> str | None:
    for module_id in candidates:
        module = modules.get(module_id)
        if module is None or module.status != "validated":
            continue
        prefix_match = not role.module_prefixes or any(
            module_id.startswith(prefix) for prefix in role.module_prefixes
        )
        kind_match = not role.kinds or module.kind in role.kinds
        if prefix_match and kind_match:
            return module_id
    return None


def build_composition_plan(
    *,
    frame: dict[str, Any],
    candidates: list[str],
    pattern: str,
    modules: dict[str, ModuleSpec],
) -> CompositionPlan | None:
    spec = PATTERNS.get(pattern)
    if spec is None:
        return None

    selected: dict[str, str] = {}
    for role in spec.roles:
        module_id = _select_module(role, candidates, modules)
        if module_id is None:
            return None
        selected[role.role] = module_id

    common_bindings: dict[str, Any] = {}
    entities = frame.get("entities") or []
    if entities:
        common_bindings["entity"] = entities[0]
    if frame.get("filters"):
        common_bindings.update(frame["filters"])

    nodes = [
        CompositionNode(
            node_id=role.role,
            module_id=selected[role.role],
            input_bindings=dict(common_bindings),
        )
        for role in spec.roles
    ]
    edges = [
        CompositionEdge(
            from_node=edge.from_role,
            from_output=edge.from_output,
            to_node=edge.to_role,
            to_input=edge.to_input,
        )
        for edge in spec.edges
    ]
    plan = CompositionPlan(
        plan_id=f"plan-{pattern}",
        nodes=nodes,
        edges=edges,
        output_node_ids=list(spec.output_roles),
        metadata={"pattern": pattern, "frame": frame},
    )
    report = validate_composition_plan(plan, modules)
    return plan if report.valid else None


def _frame_value(frame: Any, key: str, default=None):
    if isinstance(frame, dict):
        return frame.get(key, default)
    return getattr(frame, key, default)


def build_multi_metric_plan(
    *,
    frame: Any,
    candidates: list[str],
    modules: dict[str, ModuleSpec],
) -> CompositionPlan | None:
    metrics = list(_frame_value(frame, "metrics", []) or [])
    module_ids: list[str] = []
    for metric_key in metrics:
        preferred = f"metric_{metric_key}"
        if preferred in candidates and preferred in modules:
            module_ids.append(preferred)
            continue
        for candidate in candidates:
            module = modules.get(candidate)
            if module and module.kind == "metric" and candidate not in module_ids:
                module_ids.append(candidate)
                break
    if len(module_ids) < 2:
        return None

    entities = list(_frame_value(frame, "entities", []) or [])
    filters = dict(_frame_value(frame, "filters", {}) or {})
    common_bindings = {"query": " ".join(metrics), **filters}
    if entities:
        common_bindings["entity"] = entities[0]
    nodes = [
        CompositionNode(
            node_id=f"metric_{index}",
            module_id=module_id,
            input_bindings=dict(common_bindings),
        )
        for index, module_id in enumerate(module_ids, 1)
    ]
    plan = CompositionPlan(
        plan_id=f"plan-multi-metric-{'-'.join(metrics)}",
        nodes=nodes,
        output_node_ids=[node.node_id for node in nodes],
        metadata={"pattern": "multi_metric_lookup", "metrics": metrics},
    )
    report = validate_composition_plan(plan, modules)
    return plan if report.valid else None


def plan_from_frame(
    *,
    frame: Any,
    candidates: list[str],
    modules: dict[str, ModuleSpec],
) -> CompositionPlan | None:
    task_type = _frame_value(frame, "task_type", "metric_lookup")
    if task_type == "multi_metric":
        return build_multi_metric_plan(frame=frame, candidates=candidates, modules=modules)
    pattern = {
        "comparison": "metric_threshold_compare",
        "trend": "trend_then_drilldown",
        "drilldown": "trend_then_drilldown",
        "report": "report_chapter",
    }.get(task_type, "metric_lookup")
    frame_dict = frame.model_dump() if hasattr(frame, "model_dump") else dict(frame)
    return build_composition_plan(
        frame=frame_dict,
        candidates=candidates,
        pattern=pattern,
        modules=modules,
    )
