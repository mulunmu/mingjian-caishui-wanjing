"""Structured semantic frame consumed by composition planning."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SemanticFrame(BaseModel):
    policy_route: str
    speech_act: Literal[
        "question",
        "command",
        "correction",
        "feedback",
        "social",
        "refusal",
    ] = "question"
    business_domain: str = "general"
    task_type: Literal[
        "metric_lookup",
        "multi_metric",
        "comparison",
        "trend",
        "diagnosis",
        "drilldown",
        "report",
        "knowledge",
        "policy",
        "memory",
        "clarify",
    ] = "metric_lookup"
    subject_scope: Literal["individual", "cohort", "unbound", "system"] = "unbound"
    entities: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    output_requirements: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    language: str = "zh"
    safety: str = "normal"
    missing_slots: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
