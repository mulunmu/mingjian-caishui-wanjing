from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.tool_plan import ToolPlan, ToolStep


class ReportScope(BaseModel):
    industry_l1: str | None = None
    province: str | None = None
    entity_ids: list[str] = Field(default_factory=list)
    sample_mode: Literal["all", "filtered", "entities"] = "all"


class BlockPlan(BaseModel):
    block_id: str
    kind: Literal["kpi", "chart", "table", "narrative"]
    title: str = ""
    source_tool_id: str | None = None


class SectionPlan(BaseModel):
    section_id: str
    chapter_key: str
    objective: str = ""
    depends_on_sections: list[str] = Field(default_factory=list)
    steps: list[ToolStep] = Field(default_factory=list)
    blocks: list[BlockPlan] = Field(default_factory=list)


class ReportBlueprint(BaseModel):
    blueprint_id: str | None = None
    objective: str
    scope: ReportScope = Field(default_factory=ReportScope)
    sections: list[SectionPlan] = Field(default_factory=list)


class CompiledSection(BaseModel):
    section_id: str
    chapter_tool_id: str
    objective: str
    depends_on_sections: list[str] = Field(default_factory=list)
    plan: ToolPlan
    blocks: list[BlockPlan] = Field(default_factory=list)


class CompiledReportBlueprint(BaseModel):
    blueprint: ReportBlueprint
    sections: list[CompiledSection] = Field(default_factory=list)


class SectionExecution(BaseModel):
    section_id: str
    chapter_tool_id: str
    objective: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    step_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    blocks: list[BlockPlan] = Field(default_factory=list)


class ReportExecution(BaseModel):
    blueprint_id: str | None = None
    objective: str
    sections: dict[str, SectionExecution] = Field(default_factory=dict)
