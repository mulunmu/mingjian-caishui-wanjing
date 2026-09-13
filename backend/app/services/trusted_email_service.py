"""受信邮箱服务 — 邮件交付收件人白名单（PG + 内存兜底）。

来源语义（见 models/trusted_email.py）：
- `register` —— 注册邮箱，注册成功即受信。
- `verified` —— 发送到非注册邮箱时，经「验证码验证 + 勾选记住」后受信。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.urls import get_sync_engine

logger = logging.getLogger(__name__)

_trusted_fallback: dict[tuple[str, str], dict] = {}
_tables_ready = False


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def _ensure_tables() -> bool:
    global _tables_ready
    if _tables_ready:
        return True
    try:
        from app.db.session import Base
        from app.models.trusted_email import TrustedEmail

        Base.metadata.create_all(get_sync_engine(), tables=[TrustedEmail.__table__])
        _tables_ready = True
        return True
    except Exception as exc:
        logger.debug("trusted_email ensure_tables failed: %s", exc)
        return False


def add_trusted_email(user_id: str, email: str, source: str = "verified") -> bool:
    """登记受信邮箱（幂等：已存在则仅在有变化时刷新 source）。失败抛 ValueError（中文）。"""
    user_id = _norm(user_id)
    email = _norm(email)
    if not user_id or not email:
        raise ValueError("邮箱不能为空")
    now = datetime.now(timezone.utc)

    if _ensure_tables():
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            from app.models.trusted_email import TrustedEmail

            with Session(get_sync_engine()) as session:
                existing = session.execute(
                    select(TrustedEmail).where(
                        TrustedEmail.user_id == user_id,
                        TrustedEmail.email == email,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.source != source:
                        existing.source = source
                        existing.verified_at = now
                        session.commit()
                else:
                    session.add(
                        TrustedEmail(
                            user_id=user_id,
                            email=email,
                            source=source,
                            verified_at=now,
                            created_at=now,
                        )
                    )
                    session.commit()
        except Exception as exc:
            logger.debug("trusted_email PG add failed: %s", exc)

    _trusted_fallback[(user_id, email)] = {"source": source, "verified_at": now}
    return True


def is_trusted(user_id: str, email: str) -> bool:
    user_id = _norm(user_id)
    email = _norm(email)
    if not user_id or not email:
        return False
    if _ensure_tables():
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            from app.models.trusted_email import TrustedEmail

            with Session(get_sync_engine()) as session:
                found = session.execute(
                    select(TrustedEmail.id).where(
                        TrustedEmail.user_id == user_id,
                        TrustedEmail.email == email,
                    )
                ).scalar_one_or_none()
                if found is not None:
                    return True
        except Exception as exc:
            logger.debug("trusted_email PG lookup failed: %s", exc)
    return (user_id, email) in _trusted_fallback


def list_trusted_emails(user_id: str) -> list[dict]:
    user_id = _norm(user_id)
    if not user_id:
        return []
    rows: list[dict] = []
    if _ensure_tables():
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import Session

            from app.models.trusted_email import TrustedEmail

            with Session(get_sync_engine()) as session:
                recs = session.execute(
                    select(TrustedEmail)
                    .where(TrustedEmail.user_id == user_id)
                    .order_by(TrustedEmail.created_at)
                ).scalars().all()
                rows = [
                    {
                        "email": r.email,
                        "source": r.source,
                        "verified_at": r.verified_at.isoformat() if r.verified_at else None,
                    }
                    for r in recs
                ]
        except Exception as exc:
            logger.debug("trusted_email PG list failed: %s", exc)

    seen = {r["email"] for r in rows}
    for (uid, email), rec in _trusted_fallback.items():
        if uid == user_id and email not in seen:
            rows.append(
                {
                    "email": email,
                    "source": rec.get("source", "verified"),
                    "verified_at": rec.get("verified_at").isoformat() if rec.get("verified_at") else None,
                }
            )
    return rows


def remove_trusted_email(user_id: str, email: str) -> bool:
    user_id = _norm(user_id)
    email = _norm(email)
    if not user_id or not email:
        return False
    removed = False
    if _ensure_tables():
        try:
            from sqlalchemy import delete
            from sqlalchemy.orm import Session

            from app.models.trusted_email import TrustedEmail

            with Session(get_sync_engine()) as session:
                result = session.execute(
                    delete(TrustedEmail).where(
                        TrustedEmail.user_id == user_id,
                        TrustedEmail.email == email,
                    )
                )
                session.commit()
                removed = result.rowcount > 0
        except Exception as exc:
            logger.debug("trusted_email PG delete failed: %s", exc)
    if (user_id, email) in _trusted_fallback:
        del _trusted_fallback[(user_id, email)]
        removed = True
    return removed


def clear_memory_store() -> None:
    """仅供单测重置内存兜底。"""
    _trusted_fallback.clear()
