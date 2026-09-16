"""Deterministic small-percentage canary routing and response replacement."""
from __future__ import annotations

import os

from app.schemas.claim import claims_to_dict
from app.services.rollout import is_selected, normalize_percent, stable_bucket


def canary_bucket(key: str) -> int:
    return stable_bucket(key)


def _normalize_percent(percent: int | float | str | None) -> float:
    return normalize_percent(percent)


def is_canary_selected(key: str, percent: int | float) -> bool:
    return is_selected(key, percent)


def canary_percent() -> float:
    return _normalize_percent(os.getenv("SEMANTIC_CANARY_PERCENT", "0"))


async def apply_canary_result(
    legacy_result: dict,
    semantic_result,
    *,
    owner: str | None = None,
) -> dict:
    data = legacy_result.setdefault("data", {})
    status = str(getattr(semantic_result, "status", "error"))
    meta = {
        "status": status,
        "route": getattr(getattr(semantic_result, "route", None), "route", None),
        "domain": getattr(getattr(semantic_result, "route", None), "domain", None),
        "candidate_tool_ids": [
            item.tool_id for item in (getattr(semantic_result, "candidates", None) or [])
        ],
        "plan_tool_ids": [
            step.tool_id
            for step in (
                getattr(getattr(semantic_result, "plan", None), "steps", None) or []
            )
        ],
    }
    data["canary"] = meta
    if status != "answered" or not (getattr(semantic_result, "reply", None) or "").strip():
        return legacy_result

    followups = list(getattr(semantic_result, "followups", None) or [])
    reply = semantic_result.reply.strip()
    claims = claims_to_dict(list(getattr(semantic_result, "claims", None) or []))

    session_id = legacy_result.get("session_id")
    if session_id:
        from app.services import session_store

        replaced = session_store.replace_last_reply(session_id, reply, followups)
        if not replaced:
            meta["status"] = "persistence_failed"
            meta["fallback"] = "legacy"
            return legacy_result

    legacy_result["reply"] = reply
    legacy_result["reply_source"] = getattr(semantic_result, "reply_source", None) or "semantic"
    data["claims"] = claims
    data["followups"] = followups
    data["followup_items"] = [
        {"type": "query", "label": item, "params": {"query": item}}
        for item in followups
    ]

    return legacy_result
