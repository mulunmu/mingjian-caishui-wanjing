"""Persistent topic-thread memory for long conversations."""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.semantic_registry import ConversationTopic


def _loads(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bigrams(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", (text or "").lower())
    return {normalized[i : i + 2] for i in range(max(0, len(normalized) - 1))}


def _topic_id(session_id: str, turn_index: int) -> str:
    """Keep the durable primary key within the VARCHAR(64) column limit."""
    suffix = f"-topic-{turn_index}"
    raw = f"{session_id}{suffix}"
    if len(raw) <= 64:
        return raw
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:10]
    keep = 64 - len(suffix) - len(digest) - 1
    return f"{session_id[:keep]}-{digest}{suffix}"


def append_topic(
    session: Session,
    *,
    session_id: str,
    summary: str,
    entities: list[str] | None = None,
    filters: dict | None = None,
    scenario: str | None = None,
    intent: str | None = None,
    tool_plan: list | None = None,
    claim_ids: list[str] | None = None,
    parent_topic_id: str | None = None,
) -> ConversationTopic:
    active_topics = list(
        session.scalars(
            select(ConversationTopic).where(
                ConversationTopic.session_id == session_id,
                ConversationTopic.status == "active",
            )
        )
    )
    for topic in active_topics:
        topic.status = "completed"
        topic.updated_at = _now()

    max_turn = session.scalar(
        select(func.max(ConversationTopic.turn_index)).where(
            ConversationTopic.session_id == session_id
        )
    )
    topic = ConversationTopic(
        topic_id=_topic_id(session_id, int(max_turn or 0) + 1),
        session_id=session_id,
        turn_index=int(max_turn or 0) + 1,
        parent_topic_id=parent_topic_id,
        summary=summary,
        entities_json=_dump(entities or []),
        filters_json=_dump(filters or {}),
        scenario=scenario,
        intent=intent,
        tool_plan_json=_dump(tool_plan or []),
        claim_ids_json=_dump(claim_ids or []),
        status="active",
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(topic)
    session.flush()
    return topic


def append_topic_blocking(
    engine,
    *,
    session_id: str,
    summary: str,
    entities: list[str] | None = None,
    filters: dict | None = None,
    scenario: str | None = None,
    intent: str | None = None,
    tool_plan: list | None = None,
    claim_ids: list[str] | None = None,
) -> None:
    with Session(engine) as session:
        append_topic(
            session,
            session_id=session_id,
            summary=summary,
            entities=entities or [],
            filters=filters or {},
            scenario=scenario,
            intent=intent,
            tool_plan=tool_plan or [],
            claim_ids=claim_ids or [],
        )
        session.commit()


def list_topics(session: Session, session_id: str) -> list[ConversationTopic]:
    return list(
        session.scalars(
            select(ConversationTopic)
            .where(ConversationTopic.session_id == session_id)
            .order_by(ConversationTopic.turn_index)
        )
    )


def _ordinal_topic(topics: list[ConversationTopic], reference: str):
    if "上上上" in reference:
        index = -3
    elif "上上个" in reference:
        index = -2
    elif "上一个" in reference:
        index = -1
    else:
        return None
    return topics[index] if len(topics) >= abs(index) else None


def _semantic_topic(topics: list[ConversationTopic], reference: str):
    reference_grams = _bigrams(reference)
    if not reference_grams:
        return None
    scored = []
    for topic in topics:
        text = " ".join(
            [
                topic.summary,
                " ".join(_loads(topic.entities_json, [])),
                " ".join(
                    f"{k}={v}"
                    for k, v in _loads(topic.filters_json, {}).items()
                ),
                topic.scenario or "",
                topic.intent or "",
            ]
        )
        overlap = len(reference_grams & _bigrams(text))
        if overlap:
            scored.append((overlap / len(reference_grams), topic.turn_index, topic))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2]


def resolve_topic_reference(
    session: Session,
    session_id: str,
    reference: str,
) -> ConversationTopic | None:
    topics = list_topics(session, session_id)
    return _ordinal_topic(topics, reference) or _semantic_topic(topics, reference)


def resolve_topic_reference_blocking(
    engine,
    session_id: str,
    reference: str,
) -> dict | None:
    with Session(engine) as session:
        topic = resolve_topic_reference(session, session_id, reference)
        if topic is None:
            return None
        return {
            "topic_id": topic.topic_id,
            "summary": topic.summary,
            "entities": _loads(topic.entities_json, []),
            "filters": _loads(topic.filters_json, {}),
            "scenario": topic.scenario,
            "intent": topic.intent,
            "tool_plan": _loads(topic.tool_plan_json, []),
            "claim_ids": _loads(topic.claim_ids_json, []),
        }


def rollback_topic(
    session: Session,
    session_id: str,
    reference: str,
) -> ConversationTopic:
    target = resolve_topic_reference(session, session_id, reference)
    if target is None:
        raise LookupError("topic reference could not be resolved")
    for topic in list_topics(session, session_id):
        topic.status = "active" if topic.topic_id == target.topic_id else "completed"
        topic.updated_at = _now()
    session.flush()
    return target


def compose_topic_context(
    session: Session,
    session_id: str,
    *,
    reference: str,
    current_intent: str,
    current_query: str,
) -> dict:
    topic = resolve_topic_reference(session, session_id, reference)
    if topic is None:
        raise LookupError("topic reference could not be resolved")
    return {
        "entities": _loads(topic.entities_json, []),
        "filters": _loads(topic.filters_json, {}),
        "scenario": topic.scenario,
        "intent": current_intent,
        "query": current_query,
        "referenced_topic_id": topic.topic_id,
        "referenced_summary": topic.summary,
    }
