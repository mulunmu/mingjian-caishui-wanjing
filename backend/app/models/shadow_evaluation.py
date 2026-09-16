"""Persistent, privacy-minimized shadow comparison records."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ShadowEvaluationRecord(Base):
    __tablename__ = "shadow_evaluation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_digest: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    legacy_route: Mapped[str] = mapped_column(String(32))
    shadow_route: Mapped[str] = mapped_column(String(32))
    legacy_domain: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shadow_domain: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legacy_function: Mapped[str | None] = mapped_column(String(64), nullable=True)
    legacy_query_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    candidate_tool_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    expected_tool_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    route_match: Mapped[bool] = mapped_column(Boolean, default=False)
    domain_match: Mapped[bool] = mapped_column(Boolean, default=False)
    tool_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    legacy_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    shadow_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    switch_eligible: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    mismatch_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)