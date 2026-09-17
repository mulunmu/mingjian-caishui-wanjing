"""Build and refresh embeddings for validated RAG tools."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.models.semantic_embedding import SemanticEmbedding
from app.services.embedding_service import (
    FastEmbedProvider,
    content_hash,
    embedding_model_name,
    embedding_dimension,
)
from app.services.tool_rag import ToolSnapshot, load_tool_snapshot_sync


@dataclass(frozen=True)
class EmbeddingPlan:
    added: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    removed: tuple[str, ...]


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


def plan_embedding_changes(
    snapshot: ToolSnapshot,
    *,
    existing: dict[str, str],
    model_name: str,
) -> EmbeddingPlan:
    del model_name
    current = {tool.tool_id: content_hash(tool.retrieval_text) for tool in snapshot.tools}
    added = sorted(tool_id for tool_id in current if tool_id not in existing)
    updated = sorted(
        tool_id
        for tool_id, digest in current.items()
        if tool_id in existing and existing[tool_id] != digest
    )
    unchanged = sorted(
        tool_id
        for tool_id, digest in current.items()
        if tool_id in existing and existing[tool_id] == digest
    )
    removed = sorted(tool_id for tool_id in existing if tool_id not in current)
    return EmbeddingPlan(
        added=tuple(added),
        updated=tuple(updated),
        unchanged=tuple(unchanged),
        removed=tuple(removed),
    )


def build_tool_embedding_index(
    engine: Engine,
    *,
    embedder: Embedder | None = None,
    force: bool = False,
) -> dict[str, Any]:
    model_name = embedding_model_name()
    dimension = embedding_dimension()
    snapshot = load_tool_snapshot_sync(engine)
    provider = embedder or FastEmbedProvider(model_name=model_name)

    with Session(engine) as session:
        existing_rows = list(
            session.scalars(
                select(SemanticEmbedding).where(SemanticEmbedding.model_name == model_name)
            )
        )
        existing = {row.tool_id: row.content_hash for row in existing_rows}
        plan = plan_embedding_changes(snapshot, existing=existing, model_name=model_name)
        target_ids = set(plan.added) | set(plan.updated)
        if force:
            target_ids = {tool.tool_id for tool in snapshot.tools}

        tool_map = {tool.tool_id: tool for tool in snapshot.tools}
        ordered_ids = sorted(target_ids)
        vectors = provider.embed_documents([tool_map[tool_id].retrieval_text for tool_id in ordered_ids])
        for tool_id, vector in zip(ordered_ids, vectors):
            if len(vector) != dimension:
                raise ValueError(
                    f"embedding dimension mismatch for {tool_id}: expected {dimension}, got {len(vector)}"
                )
            row = session.scalar(
                select(SemanticEmbedding).where(
                    SemanticEmbedding.tool_id == tool_id,
                    SemanticEmbedding.model_name == model_name,
                )
            )
            if row is None:
                row = SemanticEmbedding(tool_id=tool_id, model_name=model_name)
                session.add(row)
            row.content_hash = content_hash(tool_map[tool_id].retrieval_text)
            row.dimension = dimension
            row.embedding = vector
            row.metadata_json = '{"kind": "' + tool_map[tool_id].kind + '"}'
            row.updated_at = datetime.now(timezone.utc)

        if plan.removed:
            session.execute(
                delete(SemanticEmbedding).where(
                    SemanticEmbedding.model_name == model_name,
                    SemanticEmbedding.tool_id.in_(plan.removed),
                )
            )
        session.commit()

    return {
        "model_name": model_name,
        "dimension": dimension,
        "tools": len(snapshot.tools),
        "added": len(plan.added),
        "updated": len(plan.updated),
        "unchanged": 0 if force else len(plan.unchanged),
        "forced": len(target_ids) if force else 0,
        "removed": len(plan.removed),
    }
