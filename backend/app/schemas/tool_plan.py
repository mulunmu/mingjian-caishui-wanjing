from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolStep(BaseModel):
    step_id: str
    tool_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class ToolPlan(BaseModel):
    mode: Literal["answer", "clarify", "report"]
    steps: list[ToolStep] = Field(default_factory=list)


class ToolPlanExecution(BaseModel):
    plan: ToolPlan
    claims: list[dict[str, Any]] = Field(default_factory=list)
    step_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
