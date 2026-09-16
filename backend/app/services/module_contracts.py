"""Typed compatibility contracts derived from validated RAG tools."""
from __future__ import annotations

from itertools import combinations
from typing import Any

from app.schemas.composition import ModuleSpec, PortSpec
from app.services.tool_rag import RagTool, ToolSnapshot


def _kind(tool: RagTool) -> str:
    if tool.kind == "chapter":
        return "chapter"
    if tool.kind == "scenario_tool":
        return "action"
    return "metric"


def _ports(tool: RagTool) -> tuple[list[PortSpec], list[PortSpec]]:
    if tool.kind == "chapter":
        return (
            [PortSpec(name="claims", data_type="claim_list")],
            [PortSpec(name="chapter", data_type="report_chapter")],
        )
    return (
        [
            PortSpec(name="query", data_type="query", required=False),
            PortSpec(name="scope", data_type="scope", required=False),
        ],
        [PortSpec(name="claims", data_type="claim_list")],
    )


def module_specs_from_snapshot(snapshot: ToolSnapshot) -> dict[str, ModuleSpec]:
    specs: dict[str, ModuleSpec] = {}
    for tool in snapshot.tools:
        inputs, outputs = _ports(tool)
        specs[tool.tool_id] = ModuleSpec(
            module_id=tool.tool_id,
            kind=_kind(tool),
            version="1",
            status="validated",
            inputs=inputs,
            outputs=outputs,
            dependencies=list(tool.dependencies),
            permissions=[],
            side_effect=False,
            cost=0.0,
            metadata={
                "scenarios": list(tool.scenarios),
                "chapter_links": list(tool.chapter_links),
                "shape": tool.shape,
            },
        )
    return specs


def _scenario_compatible(left: ModuleSpec, right: ModuleSpec) -> bool:
    left_scenarios = set(left.metadata.get("scenarios") or [])
    right_scenarios = set(right.metadata.get("scenarios") or [])
    return not left_scenarios or not right_scenarios or bool(left_scenarios & right_scenarios)


def can_compose(left: ModuleSpec, right: ModuleSpec) -> bool:
    """Allow left output to be consumed by right input under scenario constraints."""
    if not _scenario_compatible(left, right):
        return False
    right_inputs = {port.data_type for port in right.inputs}
    return any(port.data_type in right_inputs for port in left.outputs)


def build_compatibility_report(snapshot: ToolSnapshot) -> dict[str, Any]:
    specs = module_specs_from_snapshot(snapshot)
    metric_ids = [item.module_id for item in specs.values() if item.kind == "metric"]
    chapter_ids = [item.module_id for item in specs.values() if item.kind == "chapter"]
    pairs = 0
    compatible = 0
    missing_metric_to_chapter: list[tuple[str, str]] = []
    for left in specs.values():
        for right in specs.values():
            if left.module_id == right.module_id:
                continue
            pairs += 1
            if can_compose(left, right):
                compatible += 1
    for metric_id in metric_ids:
        for chapter_id in chapter_ids:
            if not can_compose(specs[metric_id], specs[chapter_id]):
                missing_metric_to_chapter.append((metric_id, chapter_id))
    triple_total = 0
    missing_metric_pair_to_chapter: list[tuple[str, str, str]] = []
    for metric_a, metric_b in combinations(metric_ids, 2):
        for chapter_id in chapter_ids:
            triple_total += 1
            if not (
                can_compose(specs[metric_a], specs[chapter_id])
                and can_compose(specs[metric_b], specs[chapter_id])
            ):
                missing_metric_pair_to_chapter.append((metric_a, metric_b, chapter_id))
    return {
        "module_count": len(specs),
        "pair_count": pairs,
        "compatible_pair_count": compatible,
        "metric_count": len(metric_ids),
        "chapter_count": len(chapter_ids),
        "metric_to_chapter_pairs": len(metric_ids) * len(chapter_ids),
        "missing_metric_to_chapter": missing_metric_to_chapter,
        "metric_pair_to_chapter_triples": triple_total,
        "missing_metric_pair_to_chapter": missing_metric_pair_to_chapter,
    }
