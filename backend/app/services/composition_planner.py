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
