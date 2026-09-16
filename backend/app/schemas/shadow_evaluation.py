from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ShadowComparison(BaseModel):
    query_digest: str
    legacy_route: str
    shadow_route: str
    legacy_domain: str | None = None
    shadow_domain: str | None = None
    legacy_function: str | None = None
    legacy_query_type: str | None = None
    candidate_tool_ids: list[str] = Field(default_factory=list)
    expected_tool_ids: list[str] = Field(default_factory=list)
    route_match: bool
    domain_match: bool
    tool_coverage: float = 0.0
    legacy_latency_ms: float = 0.0
    shadow_latency_ms: float = 0.0
    switch_eligible: bool = False
    mismatch_reasons: list[str] = Field(default_factory=list)
    policy_mode: str | None = None


class ShadowEvaluationRecordData(BaseModel):
    query_digest: str
    session_id: str | None = None
    legacy_route: str
    shadow_route: str
    legacy_domain: str | None = None
    shadow_domain: str | None = None
    legacy_function: str | None = None
    legacy_query_type: str | None = None
    candidate_tool_ids: list[str] = Field(default_factory=list)
    expected_tool_ids: list[str] = Field(default_factory=list)
    route_match: bool
    domain_match: bool
    tool_coverage: float
    legacy_latency_ms: float
    shadow_latency_ms: float
    switch_eligible: bool
    mismatch_reasons: list[str] = Field(default_factory=list)


class LegacyDialogueSnapshot(BaseModel):
    route: str
    domain: str | None = None
    function: str | None = None
    query_type: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)