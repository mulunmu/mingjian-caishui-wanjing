from __future__ import annotations

from pydantic import BaseModel, Field


class ToolCandidate(BaseModel):
    tool_id: str
    kind: str
    title: str
    description: str
    score: float
    matched_by: list[str] = Field(default_factory=list)
    required_params: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    chapter_links: list[str] = Field(default_factory=list)
    scenarios: list[str] = Field(default_factory=list)
    shape: str = ""
    retrieval_text: str = ""
