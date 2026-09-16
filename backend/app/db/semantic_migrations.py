"""Idempotent PostgreSQL migrations for the semantic registry."""
from __future__ import annotations

from sqlalchemy import Engine, text


def ensure_metric_definition_v2_columns(engine: Engine) -> None:
    statements = [
        "ALTER TABLE metric_definition ADD COLUMN IF NOT EXISTS category VARCHAR(32) NOT NULL DEFAULT 'composite'",
        "ALTER TABLE metric_definition ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE metric_definition ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'planned'",
        "ALTER TABLE metric_definition ADD COLUMN IF NOT EXISTS shape VARCHAR(64) NOT NULL DEFAULT ''",
        "ALTER TABLE metric_definition ADD COLUMN IF NOT EXISTS retrieval_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE metric_definition ADD COLUMN IF NOT EXISTS aliases_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE metric_definition ADD COLUMN IF NOT EXISTS source_tables_json TEXT NOT NULL DEFAULT '[]'",
        "CREATE INDEX IF NOT EXISTS ix_metric_definition_status ON metric_definition (status)",
        "CREATE INDEX IF NOT EXISTS ix_metric_definition_retrieval_enabled ON metric_definition (retrieval_enabled)",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
