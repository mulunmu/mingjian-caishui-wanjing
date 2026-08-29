"""轻量会话记忆 — 内存 L1 + PostgreSQL 持久化，30 分钟活跃 TTL"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TTL_SECONDS = 30 * 60

store: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _is_expired(entry: dict[str, Any]) -> bool:
    return _now() - entry.get("updated_at", 0) > TTL_SECONDS


def _cleanup_expired() -> None:
    for sid in [k for k, v in store.items() if _is_expired(v)]:
        del store[sid]


def _persist(entry: dict[str, Any]) -> None:
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ChatSessionRecord

        ts = datetime.now(timezone.utc)
        with Session(get_sync_engine()) as session:
            rec = session.get(ChatSessionRecord, entry["session_id"])
            if rec is None:
                rec = ChatSessionRecord(session_id=entry["session_id"])
            rec.last_intent = entry.get("last_intent")
            rec.last_function = entry.get("last_function")
            rec.last_dimension = entry.get("last_dimension")
            rec.industry_l1 = entry.get("industry_l1")
            rec.province = entry.get("province")
            rec.enterprise_id = entry.get("enterprise_id")
            rec.covered_functions_json = json.dumps(entry.get("covered_functions") or [], ensure_ascii=False)
            rec.history_json = json.dumps(entry.get("history") or [], ensure_ascii=False)
            custom = entry.get("custom_report")
            rec.custom_state_json = json.dumps(custom, ensure_ascii=False) if custom is not None else None
            rec.updated_at = ts
            session.merge(rec)
            session.commit()
    except Exception as exc:
        logger.warning("session PG persist failed (cross-worker context may be lost): %s", exc)


def _load_from_pg(session_id: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ChatSessionRecord

        with Session(get_sync_engine()) as session:
            rec = session.get(ChatSessionRecord, session_id)
            if not rec:
                return None
            updated = rec.updated_at.timestamp() if rec.updated_at else _now()
            if _now() - updated > TTL_SECONDS:
                return None
            history = json.loads(rec.history_json or "[]")
            last_semantic = None
            last_query_type = None
            for h in reversed(history):
                if isinstance(h, dict) and h.get("semantic"):
                    last_semantic = h.get("semantic")
                    last_query_type = h.get("query_type")
                    break
            return {
                "enterprises": [],
                "enterprise_names": [],
                "last_intent": rec.last_intent,
                "last_function": rec.last_function,
                "last_dimension": rec.last_dimension,
                "industry_l1": rec.industry_l1,
                "province": rec.province,
                "enterprise_id": getattr(rec, "enterprise_id", None),
                "covered_functions": json.loads(rec.covered_functions_json or "[]"),
                "history": history,
                "last_semantic_query": last_semantic,
                "last_query_type": last_query_type,
                "custom_report": json.loads(rec.custom_state_json) if rec.custom_state_json else None,
                "updated_at": updated,
            }
    except Exception:
        return None


def ensure_session_id(session_id: str | None) -> str:
    _cleanup_expired()
    sid = session_id or str(uuid.uuid4())
    if sid not in store or _is_expired(store[sid]):
        pg = _load_from_pg(sid)
        if pg:
            pg["session_id"] = sid
            store[sid] = pg
        else:
            store[sid] = {
                "enterprises": [],
                "enterprise_names": [],
                "last_intent": None,
                "last_function": None,
                "last_dimension": None,
                "industry_l1": None,
                "province": None,
                "enterprise_id": None,
                "conclusion_ids": [],
                "covered_functions": [],
                "history": [],
                "updated_at": _now(),
                "session_id": sid,
            }
    store[sid]["session_id"] = sid
    return sid


def get_session(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    _cleanup_expired()
    entry = store.get(session_id)
    if entry and not _is_expired(entry):
        return entry
    pg = _load_from_pg(session_id)
    if pg:
        pg["session_id"] = session_id
        store[session_id] = pg
        return pg
    store.pop(session_id, None)
    return None


def store_session(
    session_id: str,
    intent: str,
    enterprises: list[str] | None = None,
    query: str = "",
    enterprise_names: list[str] | None = None,
    *,
    function: str | None = None,
    dimension: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_id: str | None = None,
    conclusion_id: str | None = None,
    semantic_query: dict | None = None,
    custom_report: dict | None = None,
) -> None:
    _cleanup_expired()
    entry = store.get(session_id)
    if not entry or _is_expired(entry):
        entry = {
            "enterprises": [],
            "enterprise_names": [],
            "last_intent": None,
            "last_function": None,
            "last_dimension": None,
            "industry_l1": None,
            "province": None,
            "enterprise_id": None,
            "conclusion_ids": [],
            "covered_functions": [],
            "history": [],
            "updated_at": _now(),
            "session_id": session_id,
        }
        store[session_id] = entry

    if enterprises:
        entry["enterprises"] = list(enterprises)
    if enterprise_names:
        entry["enterprise_names"] = list(enterprise_names)

    fn = function or (intent.split("_")[0] if intent else None)
    dim = dimension
    entry["last_intent"] = intent
    if fn:
        entry["last_function"] = fn
        covered = list(entry.get("covered_functions") or [])
        if fn not in covered:
            covered.append(fn)
        entry["covered_functions"] = covered
    if dim:
        entry["last_dimension"] = dim
    if industry_l1:
        entry["industry_l1"] = industry_l1
    if province:
        entry["province"] = province
    if enterprise_id:
        entry["enterprise_id"] = enterprise_id
    if conclusion_id:
        ids = list(entry.get("conclusion_ids") or [])
        ids.append(conclusion_id)
        entry["conclusion_ids"] = ids[-30:]

    if semantic_query:
        entry["last_semantic_query"] = semantic_query
        entry["last_query_type"] = semantic_query.get("query_type")
        entry["last_metrics"] = semantic_query.get("metrics") or []
        entry["last_filters"] = semantic_query.get("filters") or {}

    if custom_report is not None:
        entry["custom_report"] = custom_report

    entry["history"].append(
        {
            "query": query,
            "intent": intent,
            "function": fn,
            "dimension": dim,
            "semantic": semantic_query,
            "query_type": entry.get("last_query_type"),
        }
    )
    if len(entry["history"]) > 20:
        entry["history"] = entry["history"][-20:]
    entry["updated_at"] = _now()
    _persist(entry)
