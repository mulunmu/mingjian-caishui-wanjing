from __future__ import annotations

from sqlalchemy import create_engine

from app.db.vector_migrations import ensure_vector_extension, ensure_vector_index


def test_vector_migration_fails_safely_without_postgres_extension():
    engine = create_engine("sqlite:///:memory:")
    report = ensure_vector_extension(engine)
    assert report["ok"] is False
    assert report["extension"] == "vector"
    assert report["error"]


def test_vector_index_skips_when_table_missing():
    engine = create_engine("sqlite:///:memory:")
    report = ensure_vector_index(engine)
    assert report["ok"] is False
    assert report["skipped"] == "semantic_embedding table missing"
