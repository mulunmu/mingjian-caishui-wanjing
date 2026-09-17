"""Topic state and reference resolution contracts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TopicState(BaseModel):
    topic_id: str
    session_id: str
    turn_index: int
    parent_topic_id: str | None = None
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    action: str = "analysis"
    scenario: str | None = None
    metrics: list[str] = Field(default_factory=list)
    analysis_patterns: list[str] = Field(default_factory=list)
    tool_plan: list[dict[str, Any]] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    chart_ids: list[str] = Field(default_factory=list)
    report_ids: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    match_reason: str = ""


class TopicSelection(BaseModel):
    topic_id: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class TopicResolution(BaseModel):
    status: Literal["resolved", "clarify", "not_found"]
    topic: TopicState | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    clarification_question: str | None = None
