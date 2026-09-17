"""Structured report plan assembled from chapters, blocks, metrics and claims."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ReportBlockStatus = Literal["planned", "ready", "missing", "duplicate"]


class ReportBlock(BaseModel):
    block_id: str
    block_kind: str
    title: str
    metric_keys: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    comparison_basis: str | None = None
    claim_ids: list[str] = Field(default_factory=list)
    chart_ids: list[str] = Field(default_factory=list)
    status: ReportBlockStatus = "planned"


class ReportChapter(BaseModel):
    chapter_id: str
    module_key: str
    title: str
    purpose: str = ""
    analysis_patterns: list[str] = Field(default_factory=list)
    blocks: list[ReportBlock] = Field(default_factory=list)


class ReportPlan(BaseModel):
    plan_id: str
    report_mode: Literal["fixed", "custom"] = "custom"
    title: str
    purpose: str = ""
    scope: dict[str, Any] = Field(default_factory=dict)
    chapters: list[ReportChapter] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportPlanValidationError(BaseModel):
    code: str
    message: str
    chapter_id: str | None = None
    block_id: str | None = None


class ReportPlanValidationReport(BaseModel):
    valid: bool
    errors: list[ReportPlanValidationError] = Field(default_factory=list)
    warnings: list[ReportPlanValidationError] = Field(default_factory=list)
