"""Build the typed module catalog from built-ins and the semantic tool snapshot."""
from __future__ import annotations

from app.schemas.composition import ModuleSpec, PortSpec


def _metric_module(metric_key: str, title: str = "") -> ModuleSpec:
    return ModuleSpec(
        module_id=f"metric_{metric_key}",
        kind="metric",
        version="1",
        status="validated",
        inputs=[
            PortSpec(name="entity", data_type="entity", required=False),
            PortSpec(name="filters", data_type="filters", required=False),
        ],
        outputs=[
            PortSpec(name="value", data_type="number"),
            PortSpec(name="claims", data_type="claims"),
        ],
        metadata={"title": title or metric_key},
    )


def _threshold_module(metric_key: str, title: str = "") -> ModuleSpec:
    return ModuleSpec(
        module_id=f"threshold_{metric_key}",
        kind="threshold",
        version="1",
        status="validated",
        inputs=[PortSpec(name="value", data_type="number")],
        outputs=[
            PortSpec(name="level", data_type="text"),
            PortSpec(name="claims", data_type="claims"),
        ],
        metadata={"title": title or metric_key},
    )


def _operator(module_id: str, inputs=None, outputs=None) -> ModuleSpec:
    return ModuleSpec(
        module_id=module_id,
        kind="operator",
        version="1",
        status="validated",
        inputs=[PortSpec(**item) for item in (inputs or [])],
        outputs=[PortSpec(**item) for item in (outputs or [])],
    )


def _builtin_operators() -> dict[str, ModuleSpec]:
    return {
        "operator_compare_industry": _operator(
            "operator_compare_industry",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "gap", "data_type": "number"}],
        ),
        "operator_compare_province": _operator(
            "operator_compare_province",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "gap", "data_type": "number"}],
        ),
        "operator_compare_peer": _operator(
            "operator_compare_peer",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "percentile", "data_type": "number"}],
        ),
        "operator_trend": _operator(
            "operator_trend", outputs=[{"name": "series", "data_type": "series"}]
        ),
        "operator_drilldown": _operator(
            "operator_drilldown",
            inputs=[{"name": "series", "data_type": "series"}],
            outputs=[{"name": "claims", "data_type": "claims"}],
        ),
        "operator_rank": _operator(
            "operator_rank", outputs=[{"name": "ranking", "data_type": "ranking"}]
        ),
        "operator_summary": _operator(
            "operator_summary",
            inputs=[{"name": "claims", "data_type": "claims"}],
            outputs=[{"name": "summary", "data_type": "text"}],
        ),
        "operator_root_cause": _operator(
            "operator_root_cause",
            inputs=[{"name": "claims", "data_type": "claims"}],
            outputs=[{"name": "causes", "data_type": "claims"}],
        ),
        "operator_risk_level": _operator(
            "operator_risk_level",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "level", "data_type": "text"}],
        ),
        "operator_change_rate": _operator(
            "operator_change_rate",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "rate", "data_type": "number"}],
        ),
        "operator_proportion": _operator(
            "operator_proportion",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "proportion", "data_type": "number"}],
        ),
        "operator_anomaly": _operator(
            "operator_anomaly",
            inputs=[{"name": "value", "data_type": "number"}],
            outputs=[{"name": "anomaly", "data_type": "text"}],
        ),
    }


def _builtin_knowledge_and_verifiers() -> dict[str, ModuleSpec]:
    modules: dict[str, ModuleSpec] = {}
    for module_id in (
        "knowledge_capability",
        "knowledge_product_faq",
        "knowledge_metric_definition",
        "knowledge_report_guide",
    ):
        modules[module_id] = ModuleSpec(
            module_id=module_id,
            kind="knowledge",
            version="1",
            status="validated",
            outputs=[PortSpec(name="text", data_type="text")],
        )
    for module_id in (
        "verifier_numeric",
        "verifier_claim",
        "verifier_policy",
        "verifier_report",
    ):
        modules[module_id] = ModuleSpec(
            module_id=module_id,
            kind="verifier",
            version="1",
            status="validated",
            inputs=[PortSpec(name="draft", data_type="text")],
            outputs=[PortSpec(name="valid", data_type="boolean")],
        )
    return modules


def _builtin_blocks() -> dict[str, ModuleSpec]:
    modules: dict[str, ModuleSpec] = {}
    for block in ("kpi", "chart", "table", "narrative", "matrix", "funnel", "radar", "timeline"):
        module_id = f"block_{block}"
        modules[module_id] = ModuleSpec(
            module_id=module_id,
            kind="block",
            version="1",
            status="validated",
            inputs=[PortSpec(name="claims", data_type="claims", required=False)],
            outputs=[PortSpec(name="claims", data_type="claims")],
        )
    return modules


def _catalog_from_snapshot(snapshot) -> dict[str, ModuleSpec] | None:
    if snapshot is None or not snapshot.tools:
        return None
    modules: dict[str, ModuleSpec] = {}
    for tool in snapshot.tools:
        if tool.kind in {"atomic_metric", "composite_metric"}:
            module = _metric_module(tool.tool_id.removeprefix("metric_"), tool.title)
            module.module_id = tool.tool_id
            module.metadata["aliases"] = list(tool.aliases)
            modules[tool.tool_id] = module
        elif tool.kind == "chapter":
            modules[tool.tool_id] = ModuleSpec(
                module_id=tool.tool_id,
                kind="chapter",
                version="1",
                status="validated",
                inputs=[PortSpec(name="claims", data_type="claims", required=False)],
                outputs=[PortSpec(name="block", data_type="block")],
                dependencies=list(tool.dependencies),
                metadata={"title": tool.title, "chapter_links": list(tool.chapter_links)},
            )
        elif tool.kind == "scenario_tool":
            modules[tool.tool_id] = _operator(tool.tool_id)
    return modules or None


def build_composition_catalog(snapshot=None) -> dict[str, ModuleSpec]:
    modules: dict[str, ModuleSpec] = {}
    modules.update(_builtin_operators())
    modules.update(_builtin_knowledge_and_verifiers())
    modules.update(_builtin_blocks())

    snapshot_modules = _catalog_from_snapshot(snapshot)
    if snapshot_modules:
        modules.update(snapshot_modules)
    else:
        from app.services.financial_benchmarks import FINANCIAL_RATIOS
        from app.services.metric_registry import CANONICAL_METRICS
        from app.services.report_templates import CHAPTER_REGISTRY

        for metric in CANONICAL_METRICS:
            module = _metric_module(metric["metric_key"], metric.get("name") or "")
            modules[module.module_id] = module
        for metric_key, cfg in FINANCIAL_RATIOS.items():
            module = _threshold_module(metric_key, cfg.get("label") or metric_key)
            modules[module.module_id] = module
        for chapter_key, chapter in CHAPTER_REGISTRY.items():
            module_id = f"chapter_{chapter_key}"
            modules[module_id] = ModuleSpec(
                module_id=module_id,
                kind="chapter",
                version="1",
                status="validated",
                inputs=[PortSpec(name="claims", data_type="claims", required=False)],
                outputs=[PortSpec(name="block", data_type="block")],
                metadata={"title": chapter.get("title"), "keywords": chapter.get("keywords") or []},
            )
    return modules
