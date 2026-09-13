"""受信邮箱 — 邮件交付的收件人白名单。

来源（source）：
- `register` —— 注册邮箱，注册成功即受信（验证码本身已证明所有权）。
- `verified` —— 用户主动添加并经验证码验证通过后勾选「记住」。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TrustedEmail(Base):
    """受信邮箱（owner = 登录用户邮箱；email = 被信任的收件地址）。"""

    __tablename__ = "trusted_emails"
    __table_args__ = (Index("ix_trusted_email_user_email", "user_id", "email", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="verified")  # register | verified
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
