from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.topic_memory import (
    append_topic,
    compose_topic_context,
    list_topics,
    resolve_topic_reference,
    rollback_topic,
)
from tests.test_semantic_registry_seed import _engine


def _seed_topics() -> tuple[object, list]:
    engine = _engine()
    with Session(engine) as session:
        topics = [
            append_topic(
                session,
                session_id="session-1",
                summary="制造业企业风险",
                entities=["ENT017"],
                filters={"industry_l1": "制造业"},
                scenario="warn",
                intent="fraud",
            ),
            append_topic(
                session,
                session_id="session-1",
                summary="天气询问",
                entities=[],
                filters={},
                scenario=None,
                intent="out_of_domain",
            ),
            append_topic(
                session,
                session_id="session-1",
                summary="发票虚开风险",
                entities=["ENT022"],
                filters={},
                scenario="audit",
                intent="fraud",
            ),
        ]
        session.commit()
        return engine, topics


def test_topic_order_and_previous_previous_reference():
    engine, _ = _seed_topics()
    with Session(engine) as session:
        topics = list_topics(session, "session-1")
        assert [topic.summary for topic in topics] == [
            "制造业企业风险",
            "天气询问",
            "发票虚开风险",
        ]
        resolved = resolve_topic_reference(session, "session-1", "回到上上个问题")
        assert resolved is not None
        assert resolved.summary == "天气询问"


def test_semantic_reference_can_target_older_topic():
    engine, _ = _seed_topics()
    with Session(engine) as session:
        resolved = resolve_topic_reference(
            session, "session-1", "回到刚才制造业那个问题"
        )
        assert resolved is not None
        assert resolved.summary == "制造业企业风险"


def test_rollback_changes_active_topic():
    engine, _ = _seed_topics()
    with Session(engine) as session:
        target = rollback_topic(session, "session-1", "回到上上个问题")
        session.commit()
        assert target.summary == "天气询问"
        active = [topic for topic in list_topics(session, "session-1") if topic.status == "active"]
        assert len(active) == 1
        assert active[0].summary == "天气询问"


def test_cross_topic_followup_merges_old_context_without_rollback():
    engine, _ = _seed_topics()
    with Session(engine) as session:
        before = [topic.summary for topic in list_topics(session, "session-1") if topic.status == "active"]
        context = compose_topic_context(
            session,
            "session-1",
            reference="刚才那个制造业的问题",
            current_intent="cash_flow",
            current_query="现在再看看现金流",
        )
        after = [topic.summary for topic in list_topics(session, "session-1") if topic.status == "active"]
        assert context["entities"] == ["ENT017"]
        assert context["filters"] == {"industry_l1": "制造业"}
        assert context["intent"] == "cash_flow"
        assert before == after
