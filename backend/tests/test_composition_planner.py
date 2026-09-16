from __future__ import annotations

from app.schemas.composition import ModuleSpec, PortSpec
from app.services.composition_planner import build_composition_plan
from app.services.composition_validator import validate_composition_plan


def _module(module_id, inputs=None, outputs=None, status="validated"):
    kind = "operator"
    if module_id.startswith("metric_"):
        kind = "metric"
    elif module_id.startswith("threshold_"):
        kind = "threshold"
    elif module_id.startswith("block_"):
        kind = "block"
    elif module_id.startswith("chapter_"):
        kind = "chapter"
    return ModuleSpec(
        module_id=module_id,
        kind=kind,
        version="1",
        status=status,
        inputs=[PortSpec(**item) for item in (inputs or [])],
        outputs=[PortSpec(**item) for item in (outputs or [])],
    )


def _modules():
    return {
        "metric_debt_ratio": _module(
            "metric_debt_ratio", outputs=[{"name": "value", "data_type": "number"}]
        ),
        "threshold_debt_ratio": _module(
            "threshold_debt_ratio",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "level", "data_type": "text"}],
        ),
        "operator_compare_industry": _module(
            "operator_compare_industry",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "gap", "data_type": "number"}],
        ),
        "operator_trend": _module(
            "operator_trend", outputs=[{"name": "series", "data_type": "series"}]
        ),
        "operator_drilldown": _module(
            "operator_drilldown",
            inputs=[{"name": "series", "data_type": "series"}],
            outputs=[{"name": "claims", "data_type": "claims"}],
        ),
        "block_claims": _module(
            "block_claims", outputs=[{"name": "claims", "data_type": "claims"}]
        ),
        "chapter_risk": _module(
            "chapter_risk",
            inputs=[{"name": "claims", "data_type": "claims"}],
            outputs=[{"name": "block", "data_type": "block"}],
        ),
    }


def test_planner_builds_metric_threshold_comparison_plan():
    plan = build_composition_plan(
        frame={"entities": ["ENT1"], "filters": {}},
        candidates=["metric_debt_ratio", "threshold_debt_ratio", "operator_compare_industry"],
        pattern="metric_threshold_compare",
        modules=_modules(),
    )
    assert plan is not None
    report = validate_composition_plan(plan, _modules())
    assert report.valid is True
    assert {node.module_id for node in plan.nodes} == {
        "metric_debt_ratio",
        "threshold_debt_ratio",
        "operator_compare_industry",
    }


def test_planner_never_invents_missing_module():
    plan = build_composition_plan(
        frame={},
        candidates=["metric_debt_ratio"],
        pattern="metric_threshold_compare",
        modules=_modules(),
    )
    assert plan is None


def test_planner_excludes_disabled_module():
    modules = _modules()
    modules["operator_compare_industry"] = _module(
        "operator_compare_industry",
        inputs=[{"name": "value", "data_type": "number"}],
        outputs=[{"name": "gap", "data_type": "number"}],
        status="disabled",
    )
    plan = build_composition_plan(
        frame={},
        candidates=["metric_debt_ratio", "threshold_debt_ratio", "operator_compare_industry"],
        pattern="metric_threshold_compare",
        modules=modules,
    )
    assert plan is None


def test_planner_builds_report_chapter_plan():
    plan = build_composition_plan(
        frame={"report": {"chapter": "risk"}},
        candidates=["block_claims", "chapter_risk"],
        pattern="report_chapter",
        modules=_modules(),
    )
    assert plan is not None
    assert plan.output_node_ids == ["chapter"]
