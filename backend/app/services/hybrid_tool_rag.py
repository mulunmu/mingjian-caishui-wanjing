"""Hybrid dense + BM25 retrieval with deterministic rank fusion."""
from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any, Iterable

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.semantic_embedding import SemanticEmbedding
from app.schemas.tool_rag import ToolCandidate
from app.services.embedding_service import FastEmbedProvider, embedding_model_name
from app.services.sync_runner import run_blocking
from app.services.tool_rag import (
    RagTool,
    ToolRagRetriever,
    ToolSnapshot,
    load_tool_snapshot,
    normalize_query_text,
)


_ASCII_RE = re.compile(r"[a-z0-9_]+", re.I)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def hybrid_rag_enabled() -> bool:
    return os.getenv("RAG_HYBRID_ENABLED", "false").lower() in {"1", "true", "yes"}


def tokenize_for_bm25(text: str) -> list[str]:
    normalized = (text or "").lower()
    tokens = _ASCII_RE.findall(normalized)
    for chunk in _CJK_RE.findall(normalized):
        tokens.extend(chunk)
        tokens.extend(chunk[index : index + 2] for index in range(max(0, len(chunk) - 1)))
    return [token for token in tokens if token]


def _candidate_filter(tools: Iterable[RagTool], kinds: set[str] | None, allowed_ids: set[str] | None) -> list[RagTool]:
    return [
        tool
        for tool in tools
        if (not kinds or tool.kind in kinds)
        and (allowed_ids is None or tool.tool_id in allowed_ids)
    ]


def bm25_rank(
    query: str,
    snapshot: ToolSnapshot,
    *,
    top_k: int = 20,
    kinds: set[str] | None = None,
    allowed_ids: set[str] | None = None,
) -> list[tuple[str, float]]:
    tools = _candidate_filter(snapshot.tools, kinds, allowed_ids)
    if not tools:
        return []
    corpus = [tokenize_for_bm25(tool.retrieval_text) for tool in tools]
    query_tokens = tokenize_for_bm25(query)
    if not query_tokens:
        return []
    scores = BM25Okapi(corpus).get_scores(query_tokens)
    query_set = set(query_tokens)
    combined: list[tuple[str, float]] = []
    for tool, tokens, score in zip(tools, corpus, scores):
        token_set = set(tokens)
        overlap = len(query_set & token_set) / max(1, len(query_set))
        combined.append((tool.tool_id, float(score) + 5.0 * overlap))
    ranked = sorted(
        ((tool_id, score) for tool_id, score in combined if score > 0),
        key=lambda item: (-item[1], item[0]),
    )
    return ranked[:top_k]


def fuse_rankings(
    *,
    dense: list[str],
    lexical: list[str],
    rules: list[str],
    weights: dict[str, float] | None = None,
) -> tuple[list[str], dict[str, set[str]]]:
    weights = weights or {"dense": 1.0, "lexical": 1.2, "rules": 0.8}
    scores: dict[str, float] = defaultdict(float)
    matched: dict[str, set[str]] = defaultdict(set)
    for source, ids, marker in (
        ("dense", dense, "dense"),
        ("lexical", lexical, "lexical"),
        ("rules", rules, "exact"),
    ):
        for rank, tool_id in enumerate(ids, 1):
            scores[tool_id] += weights[source] / (60.0 + rank)
            matched[tool_id].add(marker)
    ranked = sorted(scores, key=lambda tool_id: (-scores[tool_id], tool_id))
    return ranked, matched


async def _dense_rank(
    db: AsyncSession,
    query_vector: list[float],
    snapshot: ToolSnapshot,
    *,
    top_k: int,
    kinds: set[str] | None,
    allowed_ids: set[str] | None,
) -> list[str]:
    distance = SemanticEmbedding.embedding.cosine_distance(query_vector).label("distance")
    query = (
        select(SemanticEmbedding.tool_id, distance)
        .where(SemanticEmbedding.model_name == embedding_model_name())
        .order_by(distance)
        .limit(max(top_k * 3, top_k))
    )
    rows = (await db.execute(query)).all()
    tool_map = {tool.tool_id: tool for tool in snapshot.tools}
    out: list[str] = []
    for tool_id, _distance in rows:
        tool = tool_map.get(str(tool_id))
        if not tool:
            continue
        if kinds and tool.kind not in kinds:
            continue
        if allowed_ids is not None and tool.tool_id not in allowed_ids:
            continue
        out.append(tool.tool_id)
        if len(out) >= top_k:
            break
    return out


def _rule_rank(
    query: str,
    snapshot: ToolSnapshot,
    *,
    domain: str | None,
    kinds: set[str] | None,
    allowed_ids: set[str] | None,
) -> list[str]:
    candidate_ids = {tool.tool_id for tool in _candidate_filter(snapshot.tools, kinds, allowed_ids)}
    candidates = ToolRagRetriever(snapshot).retrieve(
        query,
        domain=domain,
        top_k=len(candidate_ids) or 20,
        kinds=kinds,
        executable_only=False,
    )
    return [candidate.tool_id for candidate in candidates if candidate.tool_id in candidate_ids]


def _to_candidates(
    ranked_ids: list[str],
    matched: dict[str, set[str]],
    snapshot: ToolSnapshot,
    *,
    top_k: int,
    kinds: set[str] | None,
    allowed_ids: set[str] | None,
) -> list[ToolCandidate]:
    tool_map = {tool.tool_id: tool for tool in _candidate_filter(snapshot.tools, kinds, allowed_ids)}
    out: list[ToolCandidate] = []
    for rank, tool_id in enumerate(ranked_ids, 1):
        tool = tool_map.get(tool_id)
        if not tool:
            continue
        markers = sorted(matched.get(tool_id, set()))
        out.append(
            ToolCandidate(
                tool_id=tool.tool_id,
                kind=tool.kind,
                title=tool.title,
                description=tool.description,
                score=round(1.0 / (60.0 + rank), 6),
                matched_by=markers + (["rrf"] if len(markers) > 1 else []),
                required_params=list(tool.required_params),
                dependencies=list(tool.dependencies),
                chapter_links=list(tool.chapter_links),
                scenarios=list(tool.scenarios),
                shape=tool.shape,
                retrieval_text=tool.retrieval_text,
            )
        )
        if len(out) >= top_k:
            break
    return out


async def retrieve_tools_hybrid(
    db: AsyncSession,
    query: str,
    *,
    snapshot: ToolSnapshot | None = None,
    domain: str | None = None,
    top_k: int = 8,
    kinds: set[str] | None = None,
    executable_only: bool = False,
    embedder: Any | None = None,
) -> list[ToolCandidate]:
    snapshot = snapshot or await load_tool_snapshot(db)
    allowed_ids: set[str] | None = None
    if executable_only:
        from app.services.semantic_tool_executors import semantic_executor_tool_ids

        allowed_ids = semantic_executor_tool_ids()

    lexical = [tool_id for tool_id, _ in bm25_rank(query, snapshot, top_k=max(20, top_k), kinds=kinds, allowed_ids=allowed_ids)]
    rules = _rule_rank(query, snapshot, domain=domain, kinds=kinds, allowed_ids=allowed_ids)
    if not hybrid_rag_enabled():
        return ToolRagRetriever(snapshot).retrieve(
            query,
            domain=domain,
            top_k=top_k,
            kinds=kinds,
            executable_only=executable_only,
        )

    dense: list[str] = []
    try:
        provider = embedder or FastEmbedProvider()
        query_vector = await run_blocking(provider.embed_query, query)
        dense = await _dense_rank(
            db,
            query_vector,
            snapshot,
            top_k=max(20, top_k),
            kinds=kinds,
            allowed_ids=allowed_ids,
        )
    except Exception:
        dense = []

    ranked, matched = fuse_rankings(dense=dense, lexical=lexical, rules=rules)
    candidates = _to_candidates(
        ranked,
        matched,
        snapshot,
        top_k=top_k,
        kinds=kinds,
        allowed_ids=allowed_ids,
    )
    if candidates:
        return candidates
    return ToolRagRetriever(snapshot).retrieve(
        query,
        domain=domain,
        top_k=top_k,
        kinds=kinds,
        executable_only=executable_only,
    )
