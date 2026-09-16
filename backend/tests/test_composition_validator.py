from __future__ import annotations

from app.schemas.composition import (
    CompositionEdge,
    CompositionNode,
    CompositionPlan,
    ModuleSpec,
    PortSpec,
)
from app.services.composition_validator import validate_composition_plan


def _modules() -> dict[str, ModuleSpec]:
    return {
        "metric": ModuleSpec(
            module_id="metric",
            kind="metric",
            version="1",
            status="validated",
            outputs=[PortSpec(name="value", data_type="number")],
        ),
        "compare": ModuleSpec(
            module_id="compare",
            kind="operator",
            version="1",
            status="validated",
            inputs=[PortSpec(name="value", data_type="number")],
            outputs=[PortSpec(name="gap", data_type="number")],
        ),
        "expects_text": ModuleSpec(
            module_id="expects_text",
            kind="operator",
            version="1",
            status="validated",
            inputs=[PortSpec(name="text", data_type="text")],
            outputs=[PortSpec(name="value", data_type="text")],
        ),
    }


def test_validator_accepts_valid_plan_and_orders_dependencies():
    plan = CompositionPlan(
        plan_id="p1",
        nodes=[
            CompositionNode(node_id="m", module_id="metric"),
            CompositionNode(node_id="c", module_id="compare"),
        ],
        edges=[
            CompositionEdge(
                from_node="m",
                from_output="value",
                to_node="c",
                to_input="value",
            )
        ],
        output_node_ids=["c"],
    )
    report = validate_composition_plan(plan, _modules())
    assert report.valid is True
    assert report.topological_order == ["m", "c"]


def test_validator_rejects_type_mismatch():
    plan = CompositionPlan(
        plan_id="p1",
        nodes=[
            CompositionNode(node_id="m", module_id="metric"),
            CompositionNode(node_id="t", module_id="expects_text"),
        ],
        edges=[
            CompositionEdge(
                from_node="m",
                from_output="value",
                to_node="t",
                to_input="text",
            )
        ],
        output_node_ids=["t"],
    )
    report = validate_composition_plan(plan, _modules())
    assert report.valid is False
    assert any(error.code == "port_type_mismatch" for error in report.errors)


def test_validator_rejects_cycle_and_disabled_module():
    disabled = ModuleSpec(
        module_id="disabled",
        kind="operator",
        version="1",
        status="disabled",
    )
    modules = {**_modules(), "disabled": disabled}
    plan = CompositionPlan(
        plan_id="p1",
        nodes=[
            CompositionNode(node_id="a", module_id="disabled"),
            CompositionNode(node_id="b", module_id="compare"),
        ],
        edges=[
            CompositionEdge(from_node="a", from_output="value", to_node="b", to_input="value"),
            CompositionEdge(from_node="b", from_output="gap", to_node="a", to_input="value"),
        ],
        output_node_ids=["b"],
    )
    report = validate_composition_plan(plan, modules)
    codes = {error.code for error in report.errors}
    assert "module_not_executable" in codes
    assert "plan_cycle" in codes


def test_validator_rejects_missing_required_input():
    plan = CompositionPlan(
        plan_id="p1",
        nodes=[CompositionNode(node_id="c", module_id="compare")],
        output_node_ids=["c"],
    )
    report = validate_composition_plan(plan, _modules())
    assert report.valid is False
    assert any(error.code == "missing_required_input" for error in report.errors)
