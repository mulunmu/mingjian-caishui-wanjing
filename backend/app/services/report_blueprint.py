"""Compile, persist, and execute deterministic report blueprints."""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.report_blueprint import ReportBlueprintRecord
from app.schemas.report_blueprint import (
    CompiledReportBlueprint,
    CompiledSection,
    ReportBlueprint,
    ReportExecution,
    SectionExecution,
)
from app.schemas.tool_plan import ToolPlan
from app.services.plan_execution import execute_tool_plan, validate_tool_plan
from app.services.tool_rag import ToolSnapshot


class ReportBlueprintError(ValueError):
    pass


def _tool_ids(snapshot: ToolSnapshot) -> set[str]:
    return {tool.tool_id for tool in snapshot.tools}


def _serialize(value: Any):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _dump(value: Any) -> str:
    return json.dumps(_serialize(value), ensure_ascii=False, sort_keys=True)


def _loads(raw: str, default):
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def compile_report_blueprint(
    blueprint: ReportBlueprint,
    snapshot: ToolSnapshot,
) -> CompiledReportBlueprint:
    if not blueprint.sections:
        raise ReportBlueprintError("blueprint must contain at least one section")

    section_ids = [section.section_id for section in blueprint.sections]
    if len(section_ids) != len(set(section_ids)):
        raise ReportBlueprintError("duplicate section_id")
    chapter_keys = [section.chapter_key for section in blueprint.sections]
    if len(chapter_keys) != len(set(chapter_keys)):
        raise ReportBlueprintError("duplicate chapter_key")

    available = _tool_ids(snapshot)
    compiled_sections: list[CompiledSection] = []
    for section in blueprint.sections:
        chapter_tool_id = f"chapter_{section.chapter_key}"
        if chapter_tool_id not in available:
            raise ReportBlueprintError(f"unknown chapter: {section.chapter_key}")

        step_tool_ids = {step.tool_id for step in section.steps}
        for block in section.blocks:
            if block.source_tool_id and block.source_tool_id not in step_tool_ids:
                raise ReportBlueprintError(
                    f"block {block.block_id} references tool not in section: "
                    f"{block.source_tool_id}"
                )

        plan = ToolPlan(mode="report", steps=list(section.steps))
        validate_tool_plan(plan, snapshot)
        compiled_sections.append(
            CompiledSection(
                section_id=section.section_id,
                chapter_tool_id=chapter_tool_id,
                objective=section.objective,
                plan=plan,
                blocks=list(section.blocks),
            )
        )

    return CompiledReportBlueprint(
        blueprint=blueprint,
        sections=compiled_sections,
    )


def execute_report_blueprint(
    compiled: CompiledReportBlueprint,
    snapshot: ToolSnapshot,
    tool_fns: dict[str, Callable[..., dict[str, Any]]],
) -> ReportExecution:
    sections: dict[str, SectionExecution] = {}
    for section in compiled.sections:
        execution = execute_tool_plan(section.plan, snapshot, tool_fns)
        sections[section.section_id] = SectionExecution(
            section_id=section.section_id,
            chapter_tool_id=section.chapter_tool_id,
            objective=section.objective,
            claims=execution.claims,
            step_outputs=execution.step_outputs,
            blocks=section.blocks,
        )
    return ReportExecution(
        blueprint_id=compiled.blueprint.blueprint_id,
        objective=compiled.blueprint.objective,
        sections=sections,
    )


def save_report_blueprint(
    session: Session,
    blueprint: ReportBlueprint,
    *,
    owner: str | None = None,
    session_id: str | None = None,
    blueprint_id: str | None = None,
    status: str = "active",
) -> ReportBlueprintRecord:
    resolved_id = blueprint.blueprint_id or blueprint_id or uuid.uuid4().hex
    record = session.get(ReportBlueprintRecord, resolved_id)
    now = datetime.now(timezone.utc)
    if record is None:
        record = ReportBlueprintRecord(
            blueprint_id=resolved_id,
            created_at=now,
        )
        session.add(record)

    record.owner = owner
    record.session_id = session_id
    record.objective = blueprint.objective
    record.scope_json = _dump(blueprint.scope)
    record.sections_json = _dump(blueprint.sections)
    record.version = int(record.version or 1)
    record.status = status
    record.updated_at = now
    session.flush()
    return record


def load_report_blueprint(
    session: Session,
    blueprint_id: str,
) -> ReportBlueprint | None:
    record = session.get(ReportBlueprintRecord, blueprint_id)
    if record is None or record.status != "active":
        return None
    return ReportBlueprint(
        blueprint_id=record.blueprint_id,
        objective=record.objective,
        scope=_loads(record.scope_json, {}),
        sections=_loads(record.sections_json, []),
    )