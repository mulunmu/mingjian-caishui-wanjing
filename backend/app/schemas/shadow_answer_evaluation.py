from __future__ import annotations

from pydantic import BaseModel, Field


class ShadowAnswerObservation(BaseModel):
    query_digest: str
    session_id: str | None = None
    status: str
    route: str
    domain: str | None = None
    candidate_tool_ids: list[str] = Field(default_factory=list)
    plan_tool_ids: list[str] = Field(default_factory=list)
    claim_count: int = 0
    reply_present: bool = False
    latency_ms: float = 0.0
    error: str | None = None