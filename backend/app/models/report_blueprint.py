"""Persisted report blueprints for deterministic report reruns."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReportBlueprintRecord(Base):
    __tablename__ = "report_blueprint"

    blueprint_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    objective: Mapped[str] = mapped_column(Text)
    scope_json: Mapped[str] = mapped_column(Text, default="{}")
    sections_json: Mapped[str] = mapped_column(Text, default="[]")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)