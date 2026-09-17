"""Persistent topic-thread memory for long conversations."""
from __future__ import annotations

import json
import hashlib
import math
import os
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.semantic_registry import ConversationTopic


_TOPIC_REFERENCE_MARKERS = re.compile(
    r"上一个|上上个|上上上|回到.*问题|刚才|之前|前面|上面|上述|"
    r"那个|这个|那件|这件|那次|这次|该问题|该话题|它|其"
)
_TOPIC_CORRECTION_MARKERS = re.compile(
    r"不对|不是|我说的是|改成|纠正|更正|记错|刚才说的不是"
)


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


def _reference_bigrams(reference: str) -> set[str]:
    cleaned = re.sub(
        r"那个|这个|那件|这件|事情|问题|话题|的事|刚才|之前|前面|"
        r"上面|上述|继续|再|展开|一下|一点|呢|吧|吗|呀",
        "",
        (reference or "").lower(),
    )
    return _bigrams(cleaned)


def looks_like_topic_reference(reference: str) -> bool:
    value = (reference or "").strip()
    if not value:
        return False
    if _TOPIC_REFERENCE_MARKERS.search(value):
        return True
    if _TOPIC_CORRECTION_MARKERS.search(value):
        return True
    return bool(
        re.search(
            r"第\s*[0-9一二三四五六七八九十两]+\s*(?:个)?(?:问题|轮|话题)|"
            r"往前(?:数|回)?\s*[0-9一二三四五六七八九十两]+",
            value,
        )
    )


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
    report_ids: list[str] | None = None,
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
        report_ids_json=_dump(report_ids or []),
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
    report_ids: list[str] | None = None,
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
            report_ids=report_ids or [],
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


def _ordinal_number(token: str) -> int:
    if token.isdigit():
        return int(token)
    digits = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if token == "十":
        return 10
    if token.startswith("十"):
        return 10 + digits.get(token[1:], 0)
    if token.endswith("十"):
        return digits.get(token[:-1], 0) * 10
    return digits.get(token, 0)


def _ordinal_topic(topics: list[ConversationTopic], reference: str):
    if "上上上" in reference:
        index = -3
    elif "上上个" in reference:
        index = -2
    elif "上一个" in reference:
        index = -1
    else:
        number = r"([0-9]+|[一二三四五六七八九十两]+)"
        absolute = re.search(
            rf"第\s*{number}\s*(?:个)?(?:问题|轮|话题)",
            reference,
        )
        if absolute:
            turn_index = _ordinal_number(absolute.group(1))
            return next(
                (topic for topic in topics if topic.turn_index == turn_index),
                None,
            )
        relative = re.search(
            rf"(?:往前(?:数|回)?\s*{number}|{number}\s*(?:轮|个问题).*?(?:之前|以前))",
            reference,
        )
        if not relative:
            return None
        distance = _ordinal_number(next(group for group in relative.groups() if group))
        if distance <= 0:
            return None
        index = -distance
    return topics[index] if len(topics) >= abs(index) else None


def resolve_topic_reference_details(
    session: Session,
    session_id: str,
    reference: str,
    *,
    embedder=None,
) -> dict | None:
    topics = list_topics(session, session_id)
    ordinal = _ordinal_topic(topics, reference)
    if ordinal is not None:
        return {"topic": ordinal, "score": 1.0, "reason": "ordinal"}

    reference_grams = _reference_bigrams(reference)
    scored: list[tuple[float, int, str, ConversationTopic]] = []
    for topic in topics:
        text = " ".join(
            [
                topic.summary,
                " ".join(_loads(topic.entities_json, [])),
                " ".join(
                    f"{key}={value}"
                    for key, value in _loads(topic.filters_json, {}).items()
                ),
                topic.scenario or "",
                topic.intent or "",
            ]
        )
        overlap = reference_grams & _bigrams(text)
        if not overlap:
            continue
        score = len(overlap) / max(1, len(reference_grams))
        scored.append((score, topic.turn_index, ",".join(sorted(overlap)), topic))
    semantic_scores: dict[str, float] = {}
    if os.getenv("MEMORY_SEMANTIC_ENABLED", "true").lower() in {"1", "true", "yes"}:
        provider = embedder
        if provider is None:
            try:
                from app.services.embedding_service import FastEmbedProvider

                provider = FastEmbedProvider()
            except Exception:
                provider = None
        if provider is not None and topics:
            try:
                texts = [
                    " ".join(
                        [
                            topic.summary,
                            " ".join(_loads(topic.entities_json, [])),
                            " ".join(str(v) for v in _loads(topic.filters_json, {}).values()),
                            topic.scenario or "",
                            topic.intent or "",
                        ]
                    )
                    for topic in topics
                ]
                vectors = provider.embed_documents([reference] + texts)
                query_vector = vectors[0]

                def _cosine(left: list[float], right: list[float]) -> float:
                    numerator = sum(a * b for a, b in zip(left, right))
                    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
                    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
                    return numerator / (left_norm * right_norm)

                semantic_scores = {
                    topic.topic_id: _cosine(query_vector, vectors[index + 1])
                    for index, topic in enumerate(topics)
                }
            except Exception:
                semantic_scores = {}

    combined: list[tuple[float, int, str, ConversationTopic]] = []
    keyword_by_topic = {topic.topic_id: item for item in scored for topic in [item[3]]}
    for topic in topics:
        keyword_item = keyword_by_topic.get(topic.topic_id)
        keyword_score = keyword_item[0] if keyword_item else 0.0
        keyword_reason = keyword_item[2] if keyword_item else ""
        semantic_score = float(semantic_scores.get(topic.topic_id, 0.0))
        if semantic_score < 0.45:
            semantic_score = 0.0
        if semantic_score >= keyword_score and semantic_score > 0:
            combined.append((semantic_score, topic.turn_index, "semantic", topic))
        elif keyword_score >= 0.15:
            combined.append((keyword_score, topic.turn_index, keyword_reason, topic))
    if not combined:
        return None
    combined.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, _, reason, topic = combined[0]
    return {"topic": topic, "score": round(score, 4), "reason": reason}


def compress_topic_summaries(
    topics: list[ConversationTopic],
    *,
    limit: int = 12,
    max_chars: int = 1600,
) -> str:
    """Deterministic layered compression: recent-first, de-duplicated, bounded."""
    selected = topics[-max(1, limit) :]
    by_summary: dict[str, tuple[int, str]] = {}
    for topic in selected:
        summary = (topic.summary or "").strip()
        if not summary:
            continue
        key = re.sub(r"\s+", "", summary).lower()
        by_summary[key] = (topic.turn_index, summary)
    lines = [
        f"{turn_index}:{summary}"
        for turn_index, summary in sorted(by_summary.values(), key=lambda item: item[0])
    ]
    kept_reversed: list[str] = []
    used = 0
    for line in reversed(lines):
        if kept_reversed and used + len(line) + 1 > max_chars:
            break
        kept_reversed.append(line)
        used += len(line) + 1
    return "；".join(reversed(kept_reversed))[:max_chars]


def resolve_topic_reference(
    session: Session,
    session_id: str,
    reference: str,
) -> ConversationTopic | None:
    match = resolve_topic_reference_details(session, session_id, reference)
    return match["topic"] if match else None


def resolve_topic_reference_blocking(
    engine,
    session_id: str,
    reference: str,
) -> dict | None:
    with Session(engine) as session:
        match = resolve_topic_reference_details(session, session_id, reference)
        if match is None:
            return None
        topic = match["topic"]
        return {
            "topic_id": topic.topic_id,
            "summary": topic.summary,
            "entities": _loads(topic.entities_json, []),
            "filters": _loads(topic.filters_json, {}),
            "scenario": topic.scenario,
            "intent": topic.intent,
            "tool_plan": _loads(topic.tool_plan_json, []),
            "claim_ids": _loads(topic.claim_ids_json, []),
            "report_ids": _loads(topic.report_ids_json, []),
            "match_score": match["score"],
            "match_reason": match["reason"],
        }


def compose_memory_context(
    session: Session,
    session_id: str,
    *,
    limit: int = 12,
    query: str | None = None,
    embedder=None,
) -> dict:
    """Compact durable view: summaries plus entity/filter indexes, not raw messages."""
    topics = list_topics(session, session_id)
    selected = topics[-max(1, limit) :]
    entities: list[str] = []
    filters: dict[str, list[str]] = {}
    claim_ids: list[str] = []
    report_ids: list[str] = []
    tool_plan: list = []
    recent_topics: list[dict] = []
    for topic in selected:
        for entity in _loads(topic.entities_json, []):
            if entity and entity not in entities:
                entities.append(str(entity))
        for key, value in _loads(topic.filters_json, {}).items():
            values = value if isinstance(value, list) else [value]
            bucket = filters.setdefault(str(key), [])
            for item in values:
                if item not in bucket:
                    bucket.append(item)
        for claim_id in _loads(topic.claim_ids_json, []):
            if claim_id and claim_id not in claim_ids:
                claim_ids.append(str(claim_id))
        for report_id in _loads(topic.report_ids_json, []):
            if report_id and report_id not in report_ids:
                report_ids.append(str(report_id))
        tool_plan.extend(_loads(topic.tool_plan_json, []))
        recent_topics.append(
            {
                "topic_id": topic.topic_id,
                "turn_index": topic.turn_index,
                "summary": topic.summary,
                "scenario": topic.scenario,
                "intent": topic.intent,
            }
        )
    summary = compress_topic_summaries(topics, limit=limit)
    reference_match = (
        resolve_topic_reference_details(session, session_id, query, embedder=embedder)
        if query and looks_like_topic_reference(query)
        else None
    )
    return {
        "topic_count": len(topics),
        "summarized_topic_count": len(selected),
        "session_summary": summary[:1200],
        "entities": entities,
        "filters": filters,
        "claim_ids": claim_ids,
        "report_ids": report_ids,
        "tool_plan": tool_plan,
        "recent_topics": recent_topics,
        "recent_topic_ids": [topic.topic_id for topic in selected],
        "correction_detected": bool(query and _TOPIC_CORRECTION_MARKERS.search(query)),
        "referenced_topic_id": reference_match["topic"].topic_id if reference_match else None,
        "referenced_summary": reference_match["topic"].summary if reference_match else None,
        "referenced_entities": _loads(reference_match["topic"].entities_json, []) if reference_match else [],
        "referenced_filters": _loads(reference_match["topic"].filters_json, {}) if reference_match else {},
        "referenced_scenario": reference_match["topic"].scenario if reference_match else None,
        "referenced_intent": reference_match["topic"].intent if reference_match else None,
        "referenced_tool_plan": _loads(reference_match["topic"].tool_plan_json, []) if reference_match else [],
        "referenced_claim_ids": _loads(reference_match["topic"].claim_ids_json, []) if reference_match else [],
        "referenced_report_ids": _loads(reference_match["topic"].report_ids_json, []) if reference_match else [],
        "topic_match_score": reference_match["score"] if reference_match else None,
        "topic_match_reason": reference_match["reason"] if reference_match else None,
    }


def compose_memory_context_blocking(
    engine,
    session_id: str,
    *,
    limit: int = 12,
    query: str | None = None,
    embedder=None,
) -> dict:
    with Session(engine) as session:
        return compose_memory_context(
            session,
            session_id,
            limit=limit,
            query=query,
            embedder=embedder,
        )


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
