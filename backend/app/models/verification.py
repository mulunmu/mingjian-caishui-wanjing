"""邮箱验证码 — 注册场景的一次性口令。

同一 (email, purpose) 允许存在多行历史；`consume_code` 只取最新未消费的一条，
并用 SELECT ... FOR UPDATE 串行化，保证并发下不会被消费两次。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EmailVerificationCode(Base):
    """一次性邮箱验证码（不依赖 Redis；冷却与配额全部落 PG）。"""

    __tablename__ = "email_verification_codes"
    __table_args__ = (Index("ix_verify_email_purpose", "email", "purpose"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)  # register | login | reset
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordResetTicket(Base):
    """重置密码的一次性票据 —— 只有「验证码已验证通过」才会签发。

    存在这一层的理由：`/reset-password` 若不要求票据，则任何知道邮箱的人
    都能直接改掉别人密码。票据由 jti 主键 + consumed_at 保证一次性，
    消费用 UPDATE ... WHERE consumed_at IS NULL 的 rowcount 判定，天然原子。
    """

    __tablename__ = "password_reset_tickets"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
