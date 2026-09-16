"""Explicit approvals for composition plan registry-version migrations."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CompositionMigrationApproval(Base):
    __tablename__ = "composition_migration_approval"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(String(160), index=True)
    from_version: Mapped[str] = mapped_column(String(64), index=True)
    to_version: Mapped[str] = mapped_column(String(64), index=True)
    approved_by: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="approved", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
