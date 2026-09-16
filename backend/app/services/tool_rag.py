"""Database-backed structured Tool RAG for validated semantic tools."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.semantic_registry import (
    ToolAlias,
    ToolDefinition,
    ToolDependency,
    ToolExample,
)
from app.schemas.tool_rag import ToolCandidate


_QUESTION_FILLERS = re.compile(
    r"是不是|是否|请问|帮我|帮我看看|麻烦|到底|怎么样|怎么|多少|有哪些|吗|呢|？|\?|。|！|!",
    re.IGNORECASE,
)


def normalize_query_text(text: str) -> str:
    return _QUESTION_FILLERS.sub("", (text or "").lower()).strip()


def _loads(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _bigrams(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", (text or "").lower())
    return {normalized[i : i + 2] for i in range(max(0, len(normalized) - 1))}


def _overlap(query: str, text: str) -> float:
    left = _bigrams(query)
    right = _bigrams(text)
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


@dataclass(frozen=True)
class RagTool:
    tool_id: str
    kind: str
    title: str
    description: str
    aliases: tuple[str, ...]
    examples: tuple[str, ...]
    required_params: tuple[str, ...]
    dependencies: tuple[str, ...]
    chapter_links: tuple[str, ...]
    scenarios: tuple[str, ...]
    shape: str

    @property
    def retrieval_text(self) -> str:
        return " ".join(
            [
                self.tool_id,
                self.title,
                self.description,
                *self.aliases,
                *self.examples,
            ]
        )


@dataclass(frozen=True)
class ToolSnapshot:
    tools: tuple[RagTool, ...]


def _build_snapshot(
    tools: list[ToolDefinition],
    aliases: list[ToolAlias],
    examples: list[ToolExample],
    dependencies: list[ToolDependency],
) -> ToolSnapshot:
    alias_map: dict[str, list[str]] = {}
    for item in aliases:
        alias_map.setdefault(item.tool_id, []).append(item.alias)
    example_map: dict[str, list[str]] = {}
    for item in examples:
        example_map.setdefault(item.tool_id, []).append(item.query_text)
    dependency_map: dict[str, list[str]] = {}
    for item in dependencies:
        dependency_map.setdefault(item.tool_id, []).append(item.depends_on_tool_id)

    return ToolSnapshot(
        tools=tuple(
            RagTool(
                tool_id=tool.tool_id,
                kind=tool.kind,
                title=tool.title,
                description=tool.description,
                aliases=tuple(alias_map.get(tool.tool_id, [])),
                examples=tuple(example_map.get(tool.tool_id, [])),
                required_params=tuple(_loads(tool.required_params_json, [])),
                dependencies=tuple(dependency_map.get(tool.tool_id, [])),
                chapter_links=tuple(_loads(tool.chapter_links_json, [])),
                scenarios=tuple(_loads(tool.scenarios_json, [])),
                shape=tool.shape or "",
            )
            for tool in tools
        )
    )


def load_tool_snapshot_sync(engine: Engine) -> ToolSnapshot:
    with Session(engine) as session:
        tools = list(
            session.scalars(
                select(ToolDefinition).where(
                    ToolDefinition.status == "validated",
                    ToolDefinition.enabled.is_(True),
                )
            )
        )
        if not tools:
            return ToolSnapshot(tools=())
        ids = [tool.tool_id for tool in tools]
        aliases = list(
            session.scalars(
                select(ToolAlias).where(
                    ToolAlias.tool_id.in_(ids),
                    ToolAlias.status == "validated",
                )
            )
        )
        examples = list(
            session.scalars(
                select(ToolExample).where(
                    ToolExample.tool_id.in_(ids),
                    ToolExample.status == "validated",
                )
            )
        )
        dependencies = list(
            session.scalars(
                select(ToolDependency).where(ToolDependency.tool_id.in_(ids))
            )
        )
    return _build_snapshot(tools, aliases, examples, dependencies)


async def load_tool_snapshot(db: AsyncSession) -> ToolSnapshot:
    tools = list(
        await db.scalars(
            select(ToolDefinition).where(
                ToolDefinition.status == "validated",
                ToolDefinition.enabled.is_(True),
            )
        )
    )
    if not tools:
        return ToolSnapshot(tools=())
    ids = [tool.tool_id for tool in tools]
    aliases = list(
        await db.scalars(
            select(ToolAlias).where(
                ToolAlias.tool_id.in_(ids),
                ToolAlias.status == "validated",
            )
        )
    )
    examples = list(
        await db.scalars(
            select(ToolExample).where(
                ToolExample.tool_id.in_(ids),
                ToolExample.status == "validated",
            )
        )
    )
    dependencies = list(
        await db.scalars(
            select(ToolDependency).where(ToolDependency.tool_id.in_(ids))
        )
    )
    return _build_snapshot(tools, aliases, examples, dependencies)


class ToolRagRetriever:
    def __init__(self, snapshot: ToolSnapshot, executable_tool_ids: set[str] | None = None):
        self.snapshot = snapshot
        if executable_tool_ids is None:
            from app.services.semantic_tool_executors import semantic_executor_tool_ids
            executable_tool_ids = semantic_executor_tool_ids()
        self.executable_tool_ids = executable_tool_ids

    def _score(
        self,
        normalized_query: str,
        tool: RagTool,
        domain: str | None,
    ) -> tuple[float, list[str]]:
        score = 0.0
        matched: list[str] = []
        if normalized_query == tool.tool_id.lower() or normalized_query == tool.title.lower():
            score += 120.0
            matched.append("exact")
        if tool.tool_id.lower() in normalized_query:
            score += 60.0
            matched.append("tool_id")
        if tool.title and tool.title.lower() in normalized_query:
            score += 50.0
            matched.append("title")
        alias_hits = [alias for alias in tool.aliases if alias.lower() in normalized_query]
        if alias_hits:
            score += 35.0 * len(alias_hits)
            matched.append("alias")
        example_overlap = _overlap(normalized_query, " ".join(tool.examples))
        if example_overlap:
            score += 20.0 * example_overlap
            matched.append("example")
        description_overlap = _overlap(normalized_query, tool.description)
        if description_overlap:
            score += 8.0 * description_overlap
            matched.append("description")
        retrieval_overlap = _overlap(normalized_query, tool.retrieval_text)
        if retrieval_overlap:
            score += 12.0 * retrieval_overlap
            matched.append("document")
        if domain and domain in tool.scenarios:
            score += 20.0
            matched.append("domain")
        return score, matched

    def retrieve(
        self,
        query: str,
        *,
        domain: str | None = None,
        top_k: int = 8,
        kinds: set[str] | None = None,
        executable_only: bool = False,
    ) -> list[ToolCandidate]:
        normalized = normalize_query_text(query)
        scored: list[tuple[float, RagTool, list[str]]] = []
        for tool in self.snapshot.tools:
            if kinds and tool.kind not in kinds:
                continue
            if executable_only and tool.tool_id not in self.executable_tool_ids:
                continue
            score, matched = self._score(normalized, tool, domain)
            if score > 0:
                scored.append((score, tool, matched))
        scored.sort(key=lambda item: (-item[0], item[1].tool_id))
        return [
            ToolCandidate(
                tool_id=tool.tool_id,
                kind=tool.kind,
                title=tool.title,
                description=tool.description,
                score=round(score, 6),
                matched_by=matched,
                required_params=list(tool.required_params),
                dependencies=list(tool.dependencies),
                chapter_links=list(tool.chapter_links),
                scenarios=list(tool.scenarios),
                shape=tool.shape,
                retrieval_text=tool.retrieval_text,
            )
            for score, tool, matched in scored[:top_k]
        ]


async def retrieve_tools(
    db: AsyncSession,
    query: str,
    *,
    domain: str | None = None,
    top_k: int = 8,
    kinds: set[str] | None = None,
    executable_only: bool = False,
) -> list[ToolCandidate]:
    snapshot = await load_tool_snapshot(db)
    return ToolRagRetriever(snapshot).retrieve(
        query,
        domain=domain,
        top_k=top_k,
        kinds=kinds,
        executable_only=executable_only,
    )
