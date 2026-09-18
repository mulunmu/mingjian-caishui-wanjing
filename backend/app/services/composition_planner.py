"""Deterministic planner that materializes reusable composition patterns."""
from __future__ import annotations

import hashlib
from typing import Any

from app.schemas.composition import (
    CompositionCondition,
    CompositionEdge,
    CompositionNode,
    CompositionPlan,
    ModuleSpec,
)
from app.services.composition_patterns import PATTERNS, PatternRole
from app.services.composition_validator import validate_composition_plan


DYNAMIC_ANALYSIS_PATTERNS = frozenset(
    {
        "comparison",
        "trend",
        "structure",
        "distribution",
        "ranking",
        "contribution",
        "attribution",
        "anomaly",
        "correlation",
        "stratification",
        "benchmark",
        "scenario",
        "drilldown",
        "overview",
    }
)


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
            cost_estimate=modules[selected[role.role]].cost,
            condition=(
                CompositionCondition(
                    source_node=role.condition_source_role,
                    source_output=role.condition_output,
                    operator=role.condition_operator,
                    value=role.condition_value,
                )
                if role.condition_source_role and role.condition_output and role.condition_operator
                else None
            ),
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
            cost_estimate=modules[module_id].cost,
        )
        for index, module_id in enumerate(module_ids, 1)
    ]
    plan = CompositionPlan(
        plan_id=f"plan-multi-metric-{'-'.join(metrics)}",
        nodes=nodes,
        output_node_ids=[node.node_id for node in nodes],
        metadata={
            "pattern": "multi_metric_lookup",
            "strategy": "explicit_multi_metric_dag",
            "metrics": metrics,
            "selected_tool_ids": module_ids,
        },
    )
    report = validate_composition_plan(plan, modules)
    return plan if report.valid else None


def _select_dynamic_candidates(
    *,
    candidates: list[str],
    modules: dict[str, ModuleSpec],
    max_nodes: int,
) -> list[str]:
    """Select a deterministic, scenario-diverse set of executable metric modules."""
    eligible: list[str] = []
    seen: set[str] = set()
    for module_id in candidates:
        module = modules.get(module_id)
        if module is None or module.status != "validated" or module.kind != "metric":
            continue
        if module_id in seen:
            continue
        seen.add(module_id)
        eligible.append(module_id)

    if len(eligible) <= max_nodes:
        return eligible

    selected: list[str] = []
    covered_scenarios: set[str] = set()
    for module_id in eligible:
        scenarios = {
            str(item) for item in (modules[module_id].metadata.get("scenarios") or [])
        }
        if scenarios and scenarios <= covered_scenarios:
            continue
        if scenarios & covered_scenarios:
            continue
        selected.append(module_id)
        covered_scenarios.update(scenarios)
        if len(selected) >= max_nodes:
            return selected

    for module_id in eligible:
        if module_id not in selected:
            selected.append(module_id)
        if len(selected) >= max_nodes:
            break
    return selected


def build_open_overview_plan(
    *,
    frame: Any,
    candidates: list[str],
    modules: dict[str, ModuleSpec],
    max_nodes: int = 6,
) -> CompositionPlan | None:
    """Build a candidate-driven graph for open-ended entity overview questions."""
    selected_ids = _select_dynamic_candidates(
        candidates=list(candidates or []),
        modules=modules,
        max_nodes=max(2, int(max_nodes or 2)),
    )
    if len(selected_ids) < 2:
        return None

    entities = list(_frame_value(frame, "entities", []) or [])
    filters = dict(_frame_value(frame, "filters", {}) or {})
    common_bindings: dict[str, Any] = {
        "query": " ".join(
            modules[module_id].metadata.get("title") or module_id
            for module_id in selected_ids
        ),
        **filters,
    }
    if entities:
        common_bindings["entity"] = entities[0]

    nodes = [
        CompositionNode(
            node_id=f"metric_{index}",
            module_id=module_id,
            input_bindings=dict(common_bindings),
            cost_estimate=modules[module_id].cost,
        )
        for index, module_id in enumerate(selected_ids, 1)
    ]
    digest = hashlib.sha256("\n".join(selected_ids).encode("utf-8")).hexdigest()[:12]
    plan = CompositionPlan(
        plan_id=f"plan-open-overview-{digest}",
        nodes=nodes,
        output_node_ids=[node.node_id for node in nodes],
        metadata={
            "pattern": "dynamic_open_overview",
            "strategy": "dynamic_candidate_graph",
            "candidate_tool_ids": list(candidates or []),
            "selected_tool_ids": selected_ids,
            "max_nodes": max_nodes,
        },
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
    analysis_pattern = _frame_value(frame, "analysis_pattern", "")
    if task_type == "multi_metric":
        return build_multi_metric_plan(frame=frame, candidates=candidates, modules=modules)
    if task_type == "open_overview" or analysis_pattern == "overview":
        return build_open_overview_plan(
            frame=frame,
            candidates=candidates,
            modules=modules,
        )
    if (
        analysis_pattern in DYNAMIC_ANALYSIS_PATTERNS
        or analysis_pattern.startswith("composite:")
        or task_type in {
        "distribution",
        "ranking",
        "contribution",
        "correlation",
        "benchmark",
        "scenario",
        }
    ):
        return build_open_overview_plan(
            frame=frame,
            candidates=candidates,
            modules=modules,
            max_nodes=4 if analysis_pattern in {"trend", "ranking", "drilldown"} else 6,
        )
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
