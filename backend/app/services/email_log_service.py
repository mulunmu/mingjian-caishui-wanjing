"""邮件发送日志服务 — 全程审计（PG + 内存兜底）。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.urls import get_sync_engine

logger = logging.getLogger(__name__)

_logs_fallback: dict[int, dict] = {}
_log_seq = 0
_tables_ready = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_tables() -> bool:
    global _tables_ready
    if _tables_ready:
        return True
    try:
        from app.db.session import Base
        from app.models.email_log import EmailLog

        Base.metadata.create_all(get_sync_engine(), tables=[EmailLog.__table__])
        _tables_ready = True
        return True
    except Exception as exc:
        logger.debug("email_log ensure_tables failed: %s", exc)
        return False


def record_log(
    *,
    sender: str,
    recipient: str,
    subject: str = "",
    report_id: str | None = None,
    kind: str = "report",
    provider: str = "smtp",
    status: str = "pending",
    owner: str | None = None,
) -> int:
    """落一条发送记录，返回日志 id。"""
    now = _now()
    if _ensure_tables():
        try:
            from sqlalchemy.orm import Session

            from app.models.email_log import EmailLog

            with Session(get_sync_engine()) as session:
                rec = EmailLog(
                    owner=owner,
                    sender=sender,
                    recipient=recipient,
                    subject=subject,
                    report_id=report_id,
                    kind=kind,
                    provider=provider,
                    status=status,
                    created_at=now,
                )
                session.add(rec)
                session.commit()
                return rec.id
        except Exception as exc:
            logger.debug("email_log PG record failed: %s", exc)

    global _log_seq
    _log_seq += 1
    _logs_fallback[_log_seq] = {
        "id": _log_seq,
        "owner": owner,
        "sender": sender,
        "recipient": recipient,
        "subject": subject,
        "report_id": report_id,
        "kind": kind,
        "provider": provider,
        "status": status,
        "message_id": None,
        "error": None,
        "retry_count": 0,
        "created_at": now.isoformat(),
        "sent_at": None,
    }
    return _log_seq


def update_log(
    log_id: int,
    *,
    status: str | None = None,
    message_id: str | None = None,
    error: str | None = None,
    retry_count: int | None = None,
    sent_at: datetime | None = None,
) -> bool:
    """更新发送结果（状态 / 错误 / 重试计数 / 送达时间）。"""
    changed = False
    if _ensure_tables():
        try:
            from sqlalchemy.orm import Session

            from app.models.email_log import EmailLog

            with Session(get_sync_engine()) as session:
                rec = session.get(EmailLog, log_id)
                if rec is None:
                    return False
                if status is not None:
                    rec.status = status
                if message_id is not None:
                    rec.message_id = message_id
                if error is not None:
                    rec.error = error
                if retry_count is not None:
                    rec.retry_count = retry_count
                if sent_at is not None:
                    rec.sent_at = sent_at
                session.commit()
                return True
        except Exception as exc:
            logger.debug("email_log PG update failed: %s", exc)

    rec = _logs_fallback.get(log_id)
    if rec is None:
        return False
    if status is not None:
        rec["status"] = status
        changed = True
    if message_id is not None:
        rec["message_id"] = message_id
        changed = True
    if error is not None:
        rec["error"] = error
        changed = True
    if retry_count is not None:
        rec["retry_count"] = retry_count
        changed = True
    if sent_at is not None:
        rec["sent_at"] = sent_at.isoformat()
        changed = True
    return changed


def get_log(log_id: int) -> dict | None:
    if _ensure_tables():
        try:
            from sqlalchemy.orm import Session

            from app.models.email_log import EmailLog

            with Session(get_sync_engine()) as session:
                rec = session.get(EmailLog, log_id)
                if rec is not None:
                    return _to_dict(rec)
        except Exception as exc:
            logger.debug("email_log PG get failed: %s", exc)
    rec = _logs_fallback.get(log_id)
    return dict(rec) if rec else None


def _to_dict(rec) -> dict:
    return {
        "id": rec.id,
        "owner": rec.owner,
        "sender": rec.sender,
        "recipient": rec.recipient,
        "subject": rec.subject,
        "report_id": rec.report_id,
        "kind": rec.kind,
        "provider": rec.provider,
        "status": rec.status,
        "message_id": rec.message_id,
        "error": rec.error,
        "retry_count": rec.retry_count,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "sent_at": rec.sent_at.isoformat() if rec.sent_at else None,
    }


def list_logs(
    *,
    owner: str | None = None,
    recipient: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """分页查询发送记录。"""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    items: list[dict] = []
    total = 0
    if _ensure_tables():
        try:
            from sqlalchemy import func, select
            from sqlalchemy.orm import Session

            from app.models.email_log import EmailLog

            with Session(get_sync_engine()) as session:
                stmt = select(EmailLog)
                if owner:
                    stmt = stmt.where(EmailLog.owner == owner.strip().lower())
                if recipient:
                    stmt = stmt.where(EmailLog.recipient == recipient.strip().lower())
                if kind:
                    stmt = stmt.where(EmailLog.kind == kind)
                if status:
                    stmt = stmt.where(EmailLog.status == status)
                total = session.execute(
                    select(func.count()).select_from(stmt.subquery())
                ).scalar_one()
                rows = session.execute(
                    stmt.order_by(EmailLog.id.desc()).limit(limit).offset(offset)
                ).scalars().all()
                items = [_to_dict(r) for r in rows]
                return {"items": items, "total": total}
        except Exception as exc:
            logger.debug("email_log PG list failed: %s", exc)

    rows = sorted(_logs_fallback.values(), key=lambda r: r["id"], reverse=True)
    if owner:
        rows = [r for r in rows if (r.get("owner") or "") == owner.strip().lower()]
    if recipient:
        rows = [r for r in rows if r["recipient"] == recipient.strip().lower()]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if status:
        rows = [r for r in rows if r["status"] == status]
    total = len(rows)
    items = [dict(r) for r in rows[offset : offset + limit]]
    return {"items": items, "total": total}


def mark_report_deleted(report_id: str) -> int:
    """报告被删除后，将引用该报告的日志 report_id 置空（留痕不动，仅断链）。"""
    if not report_id:
        return 0
    count = 0
    if _ensure_tables():
        try:
            from sqlalchemy import update
            from sqlalchemy.orm import Session

            from app.models.email_log import EmailLog

            with Session(get_sync_engine()) as session:
                result = session.execute(
                    update(EmailLog)
                    .where(EmailLog.report_id == report_id)
                    .values(report_id=None)
                )
                session.commit()
                count = result.rowcount
        except Exception as exc:
            logger.debug("email_log mark_report_deleted failed: %s", exc)
    for rec in _logs_fallback.values():
        if rec.get("report_id") == report_id:
            rec["report_id"] = None
            count += 1
    return count


def clear_memory_store() -> None:
    """仅供单测重置内存兜底。"""
    global _log_seq
    _logs_fallback.clear()
    _log_seq = 0
