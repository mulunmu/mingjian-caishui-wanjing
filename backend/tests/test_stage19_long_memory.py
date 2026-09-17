from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.semantic_registry import ConversationTopic
from app.services.topic_memory import (
    append_topic,
    compress_topic_summaries,
    compose_memory_context,
    looks_like_topic_reference,
    resolve_topic_reference_details,
)


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "现金流" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "税负" in text:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ConversationTopic.__table__])
    return engine


def test_compress_topic_summaries_deduplicates_and_preserves_recent_order():
    engine = _engine()
    with Session(engine) as session:
        for index in range(1, 41):
            append_topic(session, session_id="long", summary=f"话题{index}")
        topics = list(session.query(ConversationTopic).order_by(ConversationTopic.turn_index))
        compressed = compress_topic_summaries(topics, limit=12)
        assert len(compressed.split("；")) <= 12
        assert compressed.endswith("话题40")
        assert compressed.count("话题39") == 1


def test_semantic_topic_reference_recovers_content_after_many_turns():
    engine = _engine()
    with Session(engine) as session:
        append_topic(session, session_id="long", summary="现金流净额偏低")
        for index in range(2, 24):
            append_topic(session, session_id="long", summary=f"无关话题{index}")
        match = resolve_topic_reference_details(
            session,
            "long",
            "那个现金流的结论再展开",
            embedder=FakeEmbedder(),
        )
        assert match is not None
        assert match["topic"].summary == "现金流净额偏低"
        assert match["reason"] == "semantic"


def test_correction_is_detected_and_preserves_reference():
    engine = _engine()
    with Session(engine) as session:
        append_topic(session, session_id="long", summary="税负偏高")
        assert looks_like_topic_reference("不对，我说的是税负的事")
        context = compose_memory_context(
            session,
            "long",
            query="不对，我说的是税负的事",
            embedder=FakeEmbedder(),
        )
        assert context["correction_detected"] is True
        assert context["referenced_summary"] == "税负偏高"
