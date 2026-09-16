from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.tool_rag import ToolCandidate


RouteKind = Literal[
    "analysis",
    "greeting",
    "capability",
    "product_faq",
    "feedback",
    "out_of_domain",
    "abuse",
    "language_switch",
    "unknown_entity",
    "clarify",
    "refuse",
    "report",
]


class ConversationRoute(BaseModel):
    route: RouteKind
    language: str = "zh"
    safety: Literal["normal", "deescalate", "block"] = "normal"
    domain: Literal["loan", "rating", "warn", "audit", "report", "general"] | None = None
    entities: list[str] = Field(default_factory=list)
    needs_tools: bool = False
    needs_clarification: bool = False
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class ConversationPolicy(BaseModel):
    response_mode: str
    retrieve_candidates: bool
    execute_tools: bool
    allow_analysis: bool
    knowledge_namespace: str | None = None


class ConversationPolicyRegistry:
    _POLICIES = {
        "greeting": ConversationPolicy(
            response_mode="social",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
        ),
        "capability": ConversationPolicy(
            response_mode="capability",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
            knowledge_namespace="capability",
        ),
        "product_faq": ConversationPolicy(
            response_mode="product_faq",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
            knowledge_namespace="capability",
        ),
        "feedback": ConversationPolicy(
            response_mode="feedback",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
        ),
        "out_of_domain": ConversationPolicy(
            response_mode="redirect",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
        ),
        "abuse": ConversationPolicy(
            response_mode="deescalate",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
        ),
        "language_switch": ConversationPolicy(
            response_mode="language_switch",
            retrieve_candidates=True,
            execute_tools=True,
            allow_analysis=True,
        ),
        "unknown_entity": ConversationPolicy(
            response_mode="entity_not_found",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
        ),
        "refuse": ConversationPolicy(
            response_mode="refusal",
            retrieve_candidates=False,
            execute_tools=False,
            allow_analysis=False,
        ),
        "clarify": ConversationPolicy(
            response_mode="clarify",
            retrieve_candidates=True,
            execute_tools=False,
            allow_analysis=True,
        ),
        "analysis": ConversationPolicy(
            response_mode="analysis",
            retrieve_candidates=True,
            execute_tools=True,
            allow_analysis=True,
        ),
        "report": ConversationPolicy(
            response_mode="report",
            retrieve_candidates=True,
            execute_tools=True,
            allow_analysis=True,
        ),
    }

    @classmethod
    def resolve(cls, route: ConversationRoute) -> ConversationPolicy:
        if route.route == "analysis" and route.needs_clarification:
            return cls._POLICIES["clarify"]
        if route.route == "abuse" or route.safety in {"deescalate", "block"}:
            return cls._POLICIES["abuse"]
        return cls._POLICIES[route.route]


class ShadowDialogueResult(BaseModel):
    route: ConversationRoute
    policy: ConversationPolicy
    candidates: list[ToolCandidate] = Field(default_factory=list)
