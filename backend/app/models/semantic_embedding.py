"""Versioned semantic embeddings for validated RAG tools."""
from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SemanticEmbedding(Base):
    __tablename__ = "semantic_embedding"
    __table_args__ = (
        UniqueConstraint("tool_id", "model_name", name="uq_semantic_embedding_tool_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_id: Mapped[str] = mapped_column(String(96), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str] = mapped_column(String(160), index=True)
    dimension: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(512))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
