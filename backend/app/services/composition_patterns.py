"""Reusable composition patterns, not frozen module combinations."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PatternRole(BaseModel):
    role: str
    module_prefixes: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    condition_source_role: str | None = None
    condition_output: str | None = None
    condition_operator: str | None = None
    condition_value: Any = None


class PatternEdge(BaseModel):
    from_role: str
    from_output: str
    to_role: str
    to_input: str


class CompositionPattern(BaseModel):
    name: str
    roles: list[PatternRole]
    edges: list[PatternEdge] = Field(default_factory=list)
    output_roles: list[str] = Field(default_factory=list)


PATTERNS: dict[str, CompositionPattern] = {
    "metric_lookup": CompositionPattern(
        name="metric_lookup",
        roles=[PatternRole(role="metric", module_prefixes=["metric_"], kinds=["metric"])],
        output_roles=["metric"],
    ),
    "metric_threshold": CompositionPattern(
        name="metric_threshold",
        roles=[
            PatternRole(role="metric", module_prefixes=["metric_"], kinds=["metric"]),
            PatternRole(role="threshold", module_prefixes=["threshold_"], kinds=["threshold"]),
        ],
        edges=[
            PatternEdge(
                from_role="metric",
                from_output="value",
                to_role="threshold",
                to_input="value",
            )
        ],
        output_roles=["threshold"],
    ),
    "metric_threshold_compare": CompositionPattern(
        name="metric_threshold_compare",
        roles=[
            PatternRole(role="metric", module_prefixes=["metric_"], kinds=["metric"]),
            PatternRole(role="threshold", module_prefixes=["threshold_"], kinds=["threshold"]),
            PatternRole(
                role="compare",
                module_prefixes=["operator_compare"],
                kinds=["operator"],
            ),
        ],
        edges=[
            PatternEdge(
                from_role="metric",
                from_output="value",
                to_role="threshold",
                to_input="value",
            ),
            PatternEdge(
                from_role="metric",
                from_output="value",
                to_role="compare",
                to_input="value",
            ),
        ],
        output_roles=["compare"],
    ),
    "metric_threshold_compare_conditional": CompositionPattern(
        name="metric_threshold_compare_conditional",
        roles=[
            PatternRole(role="metric", module_prefixes=["metric_"], kinds=["metric"]),
            PatternRole(role="threshold", module_prefixes=["threshold_"], kinds=["threshold"]),
            PatternRole(
                role="compare",
                module_prefixes=["operator_compare"],
                kinds=["operator"],
                condition_source_role="threshold",
                condition_output="level",
                condition_operator="eq",
                condition_value="high",
            ),
        ],
        edges=[
            PatternEdge(from_role="metric", from_output="value", to_role="threshold", to_input="value"),
            PatternEdge(from_role="metric", from_output="value", to_role="compare", to_input="value"),
        ],
        output_roles=["compare"],
    ),
    "trend_then_drilldown": CompositionPattern(
        name="trend_then_drilldown",
        roles=[
            PatternRole(role="trend", module_prefixes=["operator_trend"], kinds=["operator"]),
            PatternRole(
                role="drilldown",
                module_prefixes=["operator_drilldown"],
                kinds=["operator"],
            ),
        ],
        edges=[
            PatternEdge(
                from_role="trend",
                from_output="series",
                to_role="drilldown",
                to_input="series",
            )
        ],
        output_roles=["drilldown"],
    ),
    "report_chapter": CompositionPattern(
        name="report_chapter",
        roles=[
            PatternRole(role="block", module_prefixes=["block_"], kinds=["block"]),
            PatternRole(role="chapter", module_prefixes=["chapter_"], kinds=["chapter"]),
        ],
        edges=[
            PatternEdge(
                from_role="block",
                from_output="claims",
                to_role="chapter",
                to_input="claims",
            )
        ],
        output_roles=["chapter"],
    ),
}
