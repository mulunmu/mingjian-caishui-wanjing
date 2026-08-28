"""
风控结论存储 — 内存 L1 + PostgreSQL 持久化

对话层隐藏 evidence_chain；报告层完整写出。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.schemas.claim import Claim, claims_to_dict, filter_claims

logger = logging.getLogger(__name__)

TTL_SECONDS = 60 * 60
_store: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _cleanup() -> None:
    dead = [k for k, v in _store.items() if _now() - v.get("updated_at", 0) > TTL_SECONDS]
    for k in dead:
        del _store[k]


def _persist(entry: dict[str, Any]) -> None:
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ConclusionRecord

        ts = datetime.now(timezone.utc)
        with Session(get_sync_engine()) as session:
            rec = session.get(ConclusionRecord, entry["id"])
            if rec is None:
                rec = ConclusionRecord(id=entry["id"])
            rec.session_id = entry["session_id"]
            rec.function = entry["function"]
            rec.dimension = entry["dimension"]
            rec.claims_json = json.dumps(entry["claims"], ensure_ascii=False)
            rec.followups_json = json.dumps(entry["followups"], ensure_ascii=False)
            rec.evidence_hidden = entry.get("evidence_hidden", True)
            rec.meta_json = json.dumps(entry.get("meta") or {}, ensure_ascii=False)
            rec.created_at = rec.created_at or ts
            rec.updated_at = ts
            session.merge(rec)
            session.commit()
    except Exception as exc:
        logger.warning("conclusion PG persist failed (cross-worker conclusion may be lost): %s", exc)


def _load_from_pg(conclusion_id: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ConclusionRecord

        with Session(get_sync_engine()) as session:
            rec = session.get(ConclusionRecord, conclusion_id)
            if not rec:
                return None
            return {
                "id": rec.id,
                "session_id": rec.session_id,
                "function": rec.function,
                "dimension": rec.dimension,
                "claims": json.loads(rec.claims_json or "[]"),
                "followups": json.loads(rec.followups_json or "[]"),
                "evidence_hidden": rec.evidence_hidden,
                "meta": json.loads(rec.meta_json or "{}"),
                "created_at": rec.created_at.timestamp() if rec.created_at else _now(),
                "updated_at": rec.updated_at.timestamp() if rec.updated_at else _now(),
            }
    except Exception:
        return None


def _list_session_from_pg(session_id: str) -> list[dict[str, Any]]:
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ConclusionRecord

        with Session(get_sync_engine()) as session:
            rows = session.scalars(
                select(ConclusionRecord)
                .where(ConclusionRecord.session_id == session_id)
                .order_by(ConclusionRecord.created_at)
            ).all()
        out = []
        for rec in rows:
            out.append(
                {
                    "id": rec.id,
                    "session_id": rec.session_id,
                    "function": rec.function,
                    "dimension": rec.dimension,
                    "claims": json.loads(rec.claims_json or "[]"),
                    "followups": json.loads(rec.followups_json or "[]"),
                    "evidence_hidden": rec.evidence_hidden,
                    "meta": json.loads(rec.meta_json or "{}"),
                    "created_at": rec.created_at.timestamp() if rec.created_at else 0,
                    "updated_at": rec.updated_at.timestamp() if rec.updated_at else 0,
                }
            )
        return out
    except Exception:
        return []


def save_conclusion(
    *,
    session_id: str,
    function: str,
    dimension: str,
    claims: list[Claim],
    followups: list[str],
    evidence_hidden: bool = True,
    meta: dict[str, Any] | None = None,
) -> str:
    _cleanup()
    cid = uuid.uuid4().hex[:12]
    kept = filter_claims(claims)
    entry = {
        "id": cid,
        "session_id": session_id,
        "function": function,
        "dimension": dimension,
        "claims": claims_to_dict(kept),
        "followups": list(followups),
        "evidence_hidden": evidence_hidden,
        "meta": meta or {},
        "created_at": _now(),
        "updated_at": _now(),
    }
    _store[cid] = entry
    _persist(entry)
    return cid


def get_conclusion(conclusion_id: str) -> dict[str, Any] | None:
    _cleanup()
    entry = _store.get(conclusion_id)
    if entry and _now() - entry.get("updated_at", 0) <= TTL_SECONDS:
        return entry
    pg = _load_from_pg(conclusion_id)
    if pg:
        _store[conclusion_id] = pg
        return pg
    return None


def list_session_conclusions(session_id: str) -> list[dict[str, Any]]:
    _cleanup()
    mem = [v for v in _store.values() if v.get("session_id") == session_id]
    pg = _list_session_from_pg(session_id)
    by_id = {x["id"]: x for x in pg}
    for m in mem:
        by_id[m["id"]] = m
    items = list(by_id.values())
    items.sort(key=lambda x: x.get("created_at", 0))
    return items


def covered_functions(session_id: str, dimension: str | None = None) -> set[str]:
    items = list_session_conclusions(session_id)
    out = set()
    for it in items:
        if dimension and it.get("dimension") != dimension:
            continue
        out.add(it.get("function"))
    return out
