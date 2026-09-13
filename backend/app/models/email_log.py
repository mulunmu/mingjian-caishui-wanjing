"""邮件发送日志 — 全程审计（企划书 §3.4 / §7.2）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EmailLog(Base):
    """发送记录：验证码与报告邮件统一留痕，失败可重试。"""

    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 触发发送的登录用户邮箱（多用户审计按此隔离；企划书 §3.4 之外的实用扩展）
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(500), default="")
    report_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="report")  # report | verify_code
    provider: Mapped[str] = mapped_column(String(32), default="smtp")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | sent | failed
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
