"""Deterministic validation for composition DAGs."""
from __future__ import annotations

from collections import defaultdict, deque

from app.schemas.composition import (
    CompositionPlan,
    CompositionValidationError,
    CompositionValidationReport,
    ModuleSpec,
)


MAX_PLAN_NODES = 64


def _issue(code: str, message: str, node_id: str | None = None):
    return CompositionValidationError(code=code, message=message, node_id=node_id)


def _topological_order(plan: CompositionPlan) -> tuple[list[str], bool]:
    node_ids = [node.node_id for node in plan.nodes]
    indegree = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, set[str]] = defaultdict(set)
    for edge in plan.edges:
        if edge.from_node not in indegree or edge.to_node not in indegree:
            continue
        if edge.to_node not in outgoing[edge.from_node]:
            outgoing[edge.from_node].add(edge.to_node)
            indegree[edge.to_node] += 1
    queue = deque([node_id for node_id in node_ids if indegree[node_id] == 0])
    order: list[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return order, len(order) == len(node_ids)


def validate_composition_plan(
    plan: CompositionPlan,
    modules: dict[str, ModuleSpec],
) -> CompositionValidationReport:
    errors: list[CompositionValidationError] = []
    warnings: list[CompositionValidationError] = []
    nodes = {node.node_id: node for node in plan.nodes}

    if not plan.nodes:
        errors.append(_issue("plan_empty", "composition plan must contain at least one node"))
    if len(plan.nodes) > MAX_PLAN_NODES:
        errors.append(_issue("plan_too_large", f"plan exceeds {MAX_PLAN_NODES} nodes"))
    if len(nodes) != len(plan.nodes):
        errors.append(_issue("duplicate_node_id", "node IDs must be unique"))

    for node in plan.nodes:
        module = modules.get(node.module_id)
        if module is None:
            errors.append(
                _issue("module_not_found", f"module not found: {node.module_id}", node.node_id)
            )
            continue
        if module.status != "validated":
            errors.append(
                _issue(
                    "module_not_executable",
                    f"module is not validated: {node.module_id}",
                    node.node_id,
                )
            )
        for dependency in module.dependencies:
            if dependency not in modules:
                errors.append(
                    _issue(
                        "dependency_not_found",
                        f"dependency not found: {dependency}",
                        node.node_id,
                    )
                )
        if node.condition is not None:
            condition_source = nodes.get(node.condition.source_node)
            if condition_source is None:
                errors.append(
                    _issue(
                        "condition_source_not_found",
                        f"condition source not found: {node.condition.source_node}",
                        node.node_id,
                    )
                )
            else:
                source_module = modules.get(condition_source.module_id)
                if source_module is not None and not any(
                    port.name == node.condition.source_output
                    for port in source_module.outputs
                ):
                    errors.append(
                        _issue(
                            "condition_output_not_found",
                            f"condition output not found: {node.condition.source_output}",
                            node.node_id,
                        )
                    )

    incoming = defaultdict(list)
    for edge in plan.edges:
        source = nodes.get(edge.from_node)
        target = nodes.get(edge.to_node)
        if source is None or target is None:
            errors.append(_issue("edge_node_not_found", "edge references unknown node"))
            continue
        incoming[edge.to_node].append(edge)
        source_module = modules.get(source.module_id)
        target_module = modules.get(target.module_id)
        if source_module is None or target_module is None:
            continue
        source_outputs = {port.name: port for port in source_module.outputs}
        target_inputs = {port.name: port for port in target_module.inputs}
        source_port = source_outputs.get(edge.from_output)
        target_port = target_inputs.get(edge.to_input)
        if source_port is None:
            errors.append(
                _issue(
                    "output_port_not_found",
                    f"output port not found: {source.module_id}.{edge.from_output}",
                    edge.from_node,
                )
            )
        if target_port is None:
            errors.append(
                _issue(
                    "input_port_not_found",
                    f"input port not found: {target.module_id}.{edge.to_input}",
                    edge.to_node,
                )
            )
        if source_port and target_port and source_port.data_type != target_port.data_type:
            errors.append(
                _issue(
                    "port_type_mismatch",
                    f"{source_port.data_type} cannot bind to {target_port.data_type}",
                    edge.to_node,
                )
            )

    for node in plan.nodes:
        module = modules.get(node.module_id)
        if module is None:
            continue
        bound_inputs = set(node.input_bindings)
        bound_inputs.update(edge.to_input for edge in incoming[node.node_id])
        for port in module.inputs:
            if port.required and port.name not in bound_inputs:
                errors.append(
                    _issue(
                        "missing_required_input",
                        f"required input not bound: {node.module_id}.{port.name}",
                        node.node_id,
                    )
                )

    for node_id in plan.output_node_ids:
        if node_id not in nodes:
            errors.append(_issue("output_node_not_found", f"output node not found: {node_id}"))

    order, acyclic = _topological_order(plan)
    if not acyclic:
        errors.append(_issue("plan_cycle", "composition plan contains a cycle"))

    return CompositionValidationReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        topological_order=order if acyclic else [],
    )
