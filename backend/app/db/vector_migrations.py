"""PostgreSQL pgvector extension and vector-table schema helpers."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import Engine, inspect, text

logger = logging.getLogger(__name__)


def ensure_vector_extension(engine: Engine) -> dict[str, Any]:
    """Create pgvector when available; return a safe capability report."""
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
        return {"ok": version is not None, "extension": "vector", "version": version}
    except Exception as exc:
        logger.warning("pgvector extension unavailable: %s", exc)
        return {
            "ok": False,
            "extension": "vector",
            "version": None,
            "error": str(exc),
        }


def vector_extension_available(engine: Engine) -> bool:
    return bool(ensure_vector_extension(engine).get("ok"))


def has_semantic_embedding_table(engine: Engine) -> bool:
    return "semantic_embedding" in set(inspect(engine).get_table_names())


def create_all_with_vector_fallback(engine: Engine, metadata) -> dict[str, Any]:
    """Create all tables, excluding semantic_embedding when pgvector is absent."""
    report = ensure_vector_extension(engine)
    if report.get("ok"):
        metadata.create_all(engine)
        return report
    tables = [table for table in metadata.sorted_tables if table.name != "semantic_embedding"]
    metadata.create_all(engine, tables=tables)
    return report


def ensure_vector_index(engine: Engine) -> dict[str, Any]:
    """Create an HNSW cosine index after the embedding table exists."""
    if not has_semantic_embedding_table(engine):
        return {"ok": False, "skipped": "semantic_embedding table missing"}
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_semantic_embedding_hnsw "
                    "ON semantic_embedding USING hnsw (embedding vector_cosine_ops)"
                )
            )
        return {"ok": True, "index": "ix_semantic_embedding_hnsw"}
    except Exception as exc:
        logger.warning("pgvector HNSW index unavailable: %s", exc)
        return {"ok": False, "index": "ix_semantic_embedding_hnsw", "error": str(exc)}
