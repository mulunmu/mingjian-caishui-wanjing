"""Typed composition IR for dynamic module graphs."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ModuleKind = Literal[
    "metric",
    "operator",
    "threshold",
    "knowledge",
    "chapter",
    "block",
    "action",
    "verifier",
]
ModuleStatus = Literal["planned", "draft", "validated", "deprecated", "disabled"]
ConditionOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "truthy", "falsy"]


class PortSpec(BaseModel):
    name: str
    data_type: str
    required: bool = True


class ModuleSpec(BaseModel):
    module_id: str
    kind: ModuleKind
    version: str
    status: ModuleStatus
    inputs: list[PortSpec] = Field(default_factory=list)
    outputs: list[PortSpec] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    side_effect: bool = False
    cost: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompositionNode(BaseModel):
    node_id: str
    module_id: str
    input_bindings: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    timeout_ms: int = Field(default=10000, ge=1)
    retry_count: int = Field(default=0, ge=0, le=5)
    fallback_module_id: str | None = None
    cost_estimate: float = Field(default=0.0, ge=0.0)
    condition: "CompositionCondition | None" = None


class CompositionCondition(BaseModel):
    source_node: str
    source_output: str
    operator: ConditionOperator
    value: Any = None


class CompositionEdge(BaseModel):
    from_node: str
    from_output: str
    to_node: str
    to_input: str


class CompositionPlan(BaseModel):
    plan_id: str
    nodes: list[CompositionNode] = Field(default_factory=list)
    edges: list[CompositionEdge] = Field(default_factory=list)
    output_node_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompositionValidationError(BaseModel):
    code: str
    message: str
    node_id: str | None = None


class CompositionValidationReport(BaseModel):
    valid: bool
    errors: list[CompositionValidationError] = Field(default_factory=list)
    warnings: list[CompositionValidationError] = Field(default_factory=list)
    topological_order: list[str] = Field(default_factory=list)
