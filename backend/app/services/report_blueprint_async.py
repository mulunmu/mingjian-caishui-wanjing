"""Async chapter-level execution for compiled report blueprints."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.schemas.composition import CompositionNode, CompositionPlan
from app.schemas.report_blueprint import (
    CompiledReportBlueprint,
    ReportExecution,
    SectionExecution,
)
from app.services.async_dag_runtime import AsyncDagRuntime
from app.services.composition_catalog import build_composition_catalog
from app.services.composition_validator import validate_composition_plan
from app.services.plan_execution import execute_tool_plan
from app.services.tool_rag import ToolSnapshot


async def execute_report_blueprint_async(
    compiled: CompiledReportBlueprint,
    snapshot: ToolSnapshot,
    tool_fns: dict[str, Callable[..., dict[str, Any]]],
    *,
    max_concurrency: int = 4,
) -> ReportExecution:
    modules = build_composition_catalog(snapshot)
    nodes = [
        CompositionNode(
            node_id=section.section_id,
            module_id=section.chapter_tool_id,
            depends_on=list(section.depends_on_sections),
        )
        for section in compiled.sections
    ]
    plan = CompositionPlan(
        plan_id=f"report-{compiled.blueprint.blueprint_id or 'draft'}",
        nodes=nodes,
        output_node_ids=[node.node_id for node in nodes],
    )
    validation = validate_composition_plan(plan, modules)
    if not validation.valid:
        raise ValueError(
            "invalid report composition: "
            + ", ".join(error.code for error in validation.errors)
        )

    section_map = {section.section_id: section for section in compiled.sections}

    def handler_for(section_id: str):
        section = section_map[section_id]

        async def execute(_inputs: dict[str, Any]) -> dict[str, Any]:
            result = await asyncio.to_thread(
                execute_tool_plan,
                section.plan,
                snapshot,
                tool_fns,
            )
            return result.model_dump()

        return execute

    execution = await AsyncDagRuntime(max_concurrency=max_concurrency).execute(
        plan,
        handlers={node.module_id: handler_for(node.node_id) for node in nodes},
    )
    sections: dict[str, SectionExecution] = {}
    for section in compiled.sections:
        section_execution = execution.node_results[section.section_id]
        sections[section.section_id] = SectionExecution(
            section_id=section.section_id,
            chapter_tool_id=section.chapter_tool_id,
            objective=section.objective,
            claims=section_execution.get("claims") or [],
            step_outputs=section_execution.get("step_outputs") or {},
            blocks=section.blocks,
        )
    return ReportExecution(
        blueprint_id=compiled.blueprint.blueprint_id,
        objective=compiled.blueprint.objective,
        sections=sections,
    )
