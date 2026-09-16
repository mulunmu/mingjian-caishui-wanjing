from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.claim import Claim
from app.schemas.conversation_route import ConversationPolicy, ConversationRoute
from app.schemas.tool_plan import ToolPlan
from app.schemas.tool_rag import ToolCandidate


class SemanticTurnResult(BaseModel):
    status: Literal["answered", "clarify", "abstain", "not_applicable", "error"]
    route: ConversationRoute
    policy: ConversationPolicy
    candidates: list[ToolCandidate] = Field(default_factory=list)
    plan: ToolPlan | None = None
    claims: list[Claim] = Field(default_factory=list)
    reply: str | None = None
    followups: list[str] = Field(default_factory=list)
    reply_source: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)