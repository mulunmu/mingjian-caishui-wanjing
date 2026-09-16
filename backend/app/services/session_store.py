"""轻量会话记忆 — 内存 L1 + PostgreSQL 持久化。

TTL 语义拆分（M0）：
- 活跃上下文（内存 L1）：30 分钟无更新则从内存淘汰，可从 PG 回灌。
- 历史归档（history_json）：默认保留 7 天，不再被 30 分钟清掉。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ACTIVE_TTL_SECONDS = 30 * 60
HISTORY_TTL_SECONDS = 7 * 24 * 60 * 60
# 兼容旧测试/调用方
TTL_SECONDS = ACTIVE_TTL_SECONDS

store: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _normalize_owner(owner: str | None) -> str | None:
    if owner is None:
        return None
    text = str(owner).strip().lower()
    return text or None


def _is_active_expired(entry: dict[str, Any]) -> bool:
    return _now() - float(entry.get("updated_at", 0) or 0) > ACTIVE_TTL_SECONDS


def _is_history_expired(updated_at: float | None) -> bool:
    if updated_at is None:
        return True
    return _now() - float(updated_at) > HISTORY_TTL_SECONDS


def _cleanup_expired() -> None:
    """仅清超过历史归档窗口的条目；活跃过期不再删 history。"""
    for sid in [k for k, v in store.items() if _is_history_expired(v.get("updated_at"))]:
        del store[sid]


def _history_summary(history: list[Any]) -> str:
    for item in history:
        if isinstance(item, dict):
            q = (item.get("query") or "").strip()
            if q:
                return q[:80]
    return "（空会话）"


def _entry_to_messages(history: list[Any]) -> list[dict[str, Any]]:
    """把归档 history 还原为前端可渲染的 messages。"""
    messages: list[dict[str, Any]] = []
    base_ts = int(_now() * 1000)
    for i, item in enumerate(history):
        if not isinstance(item, dict):
            continue
        query = (item.get("query") or "").strip()
        reply = (item.get("reply") or "").strip()
        ts = base_ts + i * 2
        if query:
            messages.append(
                {
                    "id": f"hist-u-{i}",
                    "role": "user",
                    "content": query,
                    "timestamp": ts,
                }
            )
        if reply:
            messages.append(
                {
                    "id": f"hist-a-{i}",
                    "role": "assistant",
                    "content": reply,
                    "timestamp": ts + 1,
                    "followups": item.get("followups") or [],
                }
            )
    return messages


def _persist(entry: dict[str, Any]) -> bool:
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ChatSessionRecord

        ts = datetime.now(timezone.utc)
        with Session(get_sync_engine()) as session:
            rec = session.get(ChatSessionRecord, entry["session_id"])
            if rec is None:
                rec = ChatSessionRecord(session_id=entry["session_id"])
            owner = _normalize_owner(entry.get("owner"))
            if owner:
                rec.owner = owner
            elif getattr(rec, "owner", None):
                entry["owner"] = rec.owner
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
            # M2：焦点栈持久化
            ds = entry.get("dialogue_state") or {}
            fh = ds.get("focus_history") if isinstance(ds, dict) else None
            rec.focus_history_json = json.dumps(fh or [], ensure_ascii=False)
            rec.updated_at = ts
            session.merge(rec)
            session.commit()
            return True
    except Exception as exc:
        logger.warning("session PG persist failed (cross-worker context may be lost): %s", exc)
        return False


def _row_to_entry(rec: Any) -> dict[str, Any] | None:
    updated = rec.updated_at.timestamp() if rec.updated_at else _now()
    if _is_history_expired(updated):
        return None
    history = json.loads(rec.history_json or "[]")
    last_semantic = None
    last_query_type = None
    for h in reversed(history):
        if isinstance(h, dict) and h.get("semantic"):
            last_semantic = h.get("semantic")
            last_query_type = h.get("query_type")
            break
    focus_history = json.loads(getattr(rec, "focus_history_json", None) or "[]")
    return {
        "session_id": rec.session_id,
        "owner": getattr(rec, "owner", None),
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
        # M2：焦点栈从 PG 恢复，并放回 dialogue_state 以参与后续路由
        "focus_history": focus_history,
        "dialogue_state": {"focus_history": focus_history},
    }


def _load_from_pg(session_id: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ChatSessionRecord

        with Session(get_sync_engine()) as session:
            rec = session.get(ChatSessionRecord, session_id)
            if not rec:
                return None
            return _row_to_entry(rec)
    except Exception:
        return None


def _empty_entry(sid: str, owner: str | None = None) -> dict[str, Any]:
    return {
        "enterprises": [],
        "enterprise_names": [],
        "last_intent": None,
        "last_function": None,
        "last_dimension": None,
        "industry_l1": None,
        "province": None,
        "enterprise_id": None,
        "dialogue_state": {
            "scope": "unbound",
            "subject": None,
            "scenario": None,
        },
        "conclusion_ids": [],
        "covered_functions": [],
        "history": [],
        "owner": _normalize_owner(owner),
        "updated_at": _now(),
        "session_id": sid,
    }


def ensure_session_id(session_id: str | None, owner: str | None = None) -> str:
    _cleanup_expired()
    sid = (session_id or "").strip() or str(uuid.uuid4())
    owner_n = _normalize_owner(owner)
    entry = store.get(sid)
    if entry is not None and not _is_history_expired(entry.get("updated_at")):
        if owner_n and entry.get("owner") and entry.get("owner") != owner_n:
            sid = str(uuid.uuid4())
            store[sid] = _empty_entry(sid, owner_n)
        else:
            if owner_n and not entry.get("owner"):
                entry["owner"] = owner_n
            store[sid]["session_id"] = sid
            return sid

    pg = _load_from_pg(sid) if sid else None
    if pg:
        if owner_n and pg.get("owner") and pg.get("owner") != owner_n:
            sid = str(uuid.uuid4())
            store[sid] = _empty_entry(sid, owner_n)
        else:
            if owner_n and not pg.get("owner"):
                pg["owner"] = owner_n
            pg["session_id"] = sid
            store[sid] = pg
    else:
        if not sid:
            sid = str(uuid.uuid4())
        store[sid] = _empty_entry(sid, owner_n)
    store[sid]["session_id"] = sid
    if owner_n and not store[sid].get("owner"):
        store[sid]["owner"] = owner_n
    return sid


def get_session(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    _cleanup_expired()
    entry = store.get(session_id)
    if entry and not _is_history_expired(entry.get("updated_at")):
        # 活跃过期时优先回灌 PG（多 worker）；失败则继续用内存归档
        if _is_active_expired(entry):
            pg = _load_from_pg(session_id)
            if pg:
                # 保留内存中可能尚未落库的 owner
                if entry.get("owner") and not pg.get("owner"):
                    pg["owner"] = entry["owner"]
                store[session_id] = pg
                return pg
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
    owner: str | None = None,
    reply: str | None = None,
    followups: list[str] | None = None,
    active_conclusion: dict | None = None,
    dialogue_state: dict | None = None,
) -> bool:
    _cleanup_expired()
    entry = store.get(session_id)
    if not entry or _is_history_expired(entry.get("updated_at")):
        entry = _empty_entry(session_id, owner)
        store[session_id] = entry

    owner_n = _normalize_owner(owner)
    if owner_n:
        entry["owner"] = owner_n

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
    if dialogue_state is not None:
        from app.services.scope_state import normalize_dialogue_state

        ds = normalize_dialogue_state(dialogue_state)
        entry["dialogue_state"] = ds
        entry["scope"] = ds.get("scope")
        entry["scenario"] = ds.get("scenario")
        if ds.get("scope") == "individual" and ds.get("subject"):
            entry["enterprise_id"] = ds["subject"].get("enterprise_id")
            entry["subject"] = ds["subject"]
        elif ds.get("scope") in ("cohort", "unbound"):
            # 显式全库/未绑定：清掉个体锚点，避免静默带回
            if ds.get("scope") == "cohort":
                entry["enterprise_id"] = None
            entry["subject"] = ds.get("subject")
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

    if active_conclusion is not None:
        entry["active_conclusion"] = active_conclusion
        entry["active_conclusion_id"] = active_conclusion.get("claim_id")

    hist_item: dict[str, Any] = {
        "query": query,
        "intent": intent,
        "function": fn,
        "dimension": dim,
        "semantic": semantic_query,
        "query_type": entry.get("last_query_type"),
    }
    if reply is not None:
        hist_item["reply"] = reply
    if followups:
        hist_item["followups"] = list(followups)[:8]
    entry["history"].append(hist_item)
    if len(entry["history"]) > 40:
        entry["history"] = entry["history"][-40:]
    entry["updated_at"] = _now()
    return _persist(entry)


def replace_last_reply(
    session_id: str,
    reply: str,
    followups: list[str] | None = None,
) -> bool:
    """Replace the latest persisted assistant reply after a canary override."""
    entry = store.get(session_id) or _load_from_pg(session_id)
    if entry is None:
        return False
    history = entry.get("history") or []
    for item in reversed(history):
        if isinstance(item, dict):
            item["reply"] = reply
            if followups is not None:
                item["followups"] = list(followups)[:8]
            entry["updated_at"] = _now()
            store[session_id] = entry
            return _persist(entry)
    return False

def list_sessions(owner: str, limit: int = 20) -> list[dict[str, Any]]:
    """按 owner 返回最近会话：sid + 首条摘要 + updated_at。"""
    owner_n = _normalize_owner(owner)
    if not owner_n:
        return []
    limit = max(1, min(int(limit or 20), 50))
    items: list[dict[str, Any]] = []

    try:
        from sqlalchemy import desc
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ChatSessionRecord

        with Session(get_sync_engine()) as session:
            rows = (
                session.query(ChatSessionRecord)
                .filter(ChatSessionRecord.owner == owner_n)
                .order_by(desc(ChatSessionRecord.updated_at))
                .limit(limit * 2)
                .all()
            )
            for rec in rows:
                entry = _row_to_entry(rec)
                if not entry:
                    continue
                history = entry.get("history") or []
                items.append(
                    {
                        "session_id": rec.session_id,
                        "summary": _history_summary(history),
                        "updated_at": datetime.fromtimestamp(
                            float(entry["updated_at"]), tz=timezone.utc
                        ).isoformat(),
                        "message_count": len(_entry_to_messages(history)),
                    }
                )
                if len(items) >= limit:
                    break
    except Exception as exc:
        logger.debug("list_sessions PG failed, fallback memory: %s", exc)

    if items:
        return items[:limit]

    # 无 PG 时回退内存（单测 / 本地）
    mem: list[dict[str, Any]] = []
    for sid, entry in store.items():
        if _normalize_owner(entry.get("owner")) != owner_n:
            continue
        if _is_history_expired(entry.get("updated_at")):
            continue
        history = entry.get("history") or []
        mem.append(
            {
                "session_id": sid,
                "summary": _history_summary(history),
                "updated_at": datetime.fromtimestamp(
                    float(entry.get("updated_at") or _now()), tz=timezone.utc
                ).isoformat(),
                "message_count": len(_entry_to_messages(history)),
                "_sort": float(entry.get("updated_at") or 0),
            }
        )
    mem.sort(key=lambda x: x.pop("_sort", 0), reverse=True)
    return mem[:limit]


def load_history(owner: str, session_id: str) -> dict[str, Any] | None:
    """校验归属后返回历史消息（供前端恢复）。"""
    owner_n = _normalize_owner(owner)
    sid = (session_id or "").strip()
    if not owner_n or not sid:
        return None

    entry = get_session(sid)
    if entry is None:
        return None
    entry_owner = _normalize_owner(entry.get("owner"))
    if entry_owner and entry_owner != owner_n:
        return None
    # 无 owner 的旧会话：仅当内存/PG 无主时允许当前用户认领一次
    if not entry_owner:
        entry["owner"] = owner_n
        _persist(entry)

    history = entry.get("history") or []
    return {
        "session_id": sid,
        "owner": owner_n,
        "history": history,
        "messages": _entry_to_messages(history),
        "updated_at": datetime.fromtimestamp(
            float(entry.get("updated_at") or _now()), tz=timezone.utc
        ).isoformat(),
        "last_function": entry.get("last_function"),
        "last_dimension": entry.get("last_dimension"),
        "enterprise_id": entry.get("enterprise_id"),
        "covered_functions": entry.get("covered_functions") or [],
    }


def delete_session(owner: str, session_id: str) -> bool:
    owner_n = _normalize_owner(owner)
    sid = (session_id or "").strip()
    if not owner_n or not sid:
        return False

    entry = store.get(sid) or _load_from_pg(sid)
    if entry is None:
        return False
    entry_owner = _normalize_owner(entry.get("owner"))
    if entry_owner and entry_owner != owner_n:
        return False

    store.pop(sid, None)
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.engine_store import ChatSessionRecord

        with Session(get_sync_engine()) as session:
            rec = session.get(ChatSessionRecord, sid)
            if rec is None:
                return True
            rec_owner = _normalize_owner(getattr(rec, "owner", None))
            if rec_owner and rec_owner != owner_n:
                return False
            session.delete(rec)
            session.commit()
            return True
    except Exception as exc:
        logger.warning("delete_session PG failed: %s", exc)
        return True
