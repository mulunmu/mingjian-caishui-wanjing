"""LLM-produced, deterministically validated semantic execution plan."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.semantic_action import SemanticAction

PlanScope = Literal["individual", "cohort", "unbound", "system"]
ReferenceKind = Literal[
    "topic",
    "entity",
    "filter",
    "metric",
    "claim",
    "chart",
    "report",
]


class SemanticReference(BaseModel):
    kind: ReferenceKind
    ref_id: str
    label: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class SemanticPlanStep(BaseModel):
    step_id: str
    tool_id: str
    purpose: str = ""
    entity: str | None = None
    dimension: str | None = None
    filters: dict[str, list[str]] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("filters", mode="before")
    @classmethod
    def normalize_filters(cls, value):
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, list[str]] = {}
        for key, item in value.items():
            if isinstance(item, list):
                values = [str(part).strip() for part in item if str(part).strip()]
            elif item is None:
                values = []
            else:
                text = str(item).strip()
                values = [text] if text else []
            if values:
                normalized[str(key)] = values
        return normalized


class SemanticPlan(BaseModel):
    action: SemanticAction = SemanticAction.ANALYSIS
    route_hint: str | None = None
    planner_version: str = "semantic-plan-v2"
    policy_tags: list[str] = Field(default_factory=list)
    scope: PlanScope = "unbound"
    entities: list[str] = Field(default_factory=list)
    resolved_references: list[SemanticReference] = Field(default_factory=list)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)
    analysis_patterns: list[str] = Field(default_factory=list)
    comparison_basis: str | None = None
    steps: list[SemanticPlanStep] = Field(default_factory=list)
    output_requirements: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguous: bool = False
    ambiguity_reason: str | None = None
    clarification_question: str | None = None
    requires_confirmation: bool = False
    report_plan: dict[str, Any] | None = None
    plan_summary: str = ""
    planner_notes: list[str] = Field(default_factory=list)
    repair_history: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action_alias(cls, value):
        if isinstance(value, str) and value.strip().lower() == "inventory":
            return SemanticAction.METADATA_QUERY.value
        return value

    @field_validator("filters", mode="before")
    @classmethod
    def normalize_filters(cls, value):
        return SemanticPlanStep.normalize_filters(value)


class SemanticPlanValidationError(BaseModel):
    code: str
    message: str
    step_id: str | None = None


class SemanticPlanValidationReport(BaseModel):
    valid: bool
    errors: list[SemanticPlanValidationError] = Field(default_factory=list)
    warnings: list[SemanticPlanValidationError] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
