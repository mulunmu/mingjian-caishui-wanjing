"""Privacy-minimized observations of semantic answer composition in shadow mode."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ShadowAnswerObservationRecord(Base):
    __tablename__ = "shadow_answer_observation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_digest: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    route: Mapped[str] = mapped_column(String(32))
    domain: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candidate_tool_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    plan_tool_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_present: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)