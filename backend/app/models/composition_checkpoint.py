"""Durable checkpoints for in-progress composition DAG execution."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CompositionExecutionCheckpoint(Base):
    __tablename__ = "composition_execution_checkpoint"

    execution_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(160), index=True)
    registry_version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    state_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
