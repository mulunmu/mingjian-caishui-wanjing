"""Small, stable action contract for LLM-first semantic execution."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class SemanticAction(str, Enum):
    ANALYSIS = "analysis"
    METADATA_QUERY = "metadata_query"
    PROFILE = "profile"
    REPORT = "report"
    CONVERSATION = "conversation"
    CLARIFY = "clarify"
    REFUSE = "refuse"


class SemanticPolicyDecision(BaseModel):
    response_mode: str
    retrieve_knowledge: bool = False
    execute_tools: bool = False
    allow_analysis: bool = False
    allow_report: bool = False
    requires_confirmation: bool = False


SafetyLevel = Literal["normal", "deescalate", "block"]
