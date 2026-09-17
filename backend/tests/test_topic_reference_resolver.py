from __future__ import annotations

import pytest

from app.schemas.topic_state import TopicState
from app.services.topic_reference_resolver import resolve_topic_candidates


def _topic(topic_id: str, score: float, summary: str) -> TopicState:
    return TopicState(
        topic_id=topic_id,
        session_id="s1",
        turn_index=int(topic_id.split("-")[-1]),
        summary=summary,
        entities=["企业1"],
        filters={"industry_l1": ["制造"]},
        action="analysis",
        metrics=["authenticity_score"],
        claim_ids=[f"claim-{topic_id}"],
        score=score,
        match_reason="semantic",
    )


def test_clear_top_candidate_resolves_without_llm():
    called = False

    def selector(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"topic_id": "topic-1"}

    result = resolve_topic_candidates(
        "继续刚才那个分析",
        [_topic("topic-1", 0.92, "制造真实性"), _topic("topic-2", 0.51, "税务")],
        llm_selector=selector,
    )

    assert result.status == "resolved"
    assert result.topic is not None
    assert result.topic.topic_id == "topic-1"
    assert called is False


def test_close_candidates_use_llm_selector():
    def selector(reference, candidates):
        assert reference == "继续那个"
        assert {item.topic_id for item in candidates} == {"topic-1", "topic-2"}
        return {"topic_id": "topic-2", "confidence": 0.88}

    result = resolve_topic_candidates(
        "继续那个",
        [_topic("topic-1", 0.81, "制造真实性"), _topic("topic-2", 0.79, "制造发票")],
        llm_selector=selector,
    )

    assert result.status == "resolved"
    assert result.topic is not None
    assert result.topic.topic_id == "topic-2"
    assert result.reason == "llm"


def test_close_candidates_without_llm_require_clarification():
    result = resolve_topic_candidates(
        "继续那个",
        [_topic("topic-1", 0.70, "制造真实性"), _topic("topic-2", 0.69, "制造发票")],
        llm_selector=None,
        allow_llm=False,
    )

    assert result.status == "clarify"
    assert result.topic is None
    assert result.clarification_question


def test_invalid_llm_topic_id_is_rejected():
    def selector(*_args, **_kwargs):
        return {"topic_id": "topic-does-not-exist", "confidence": 0.99}

    result = resolve_topic_candidates(
        "继续那个",
        [_topic("topic-1", 0.70, "制造真实性"), _topic("topic-2", 0.69, "制造发票")],
        llm_selector=selector,
    )

    assert result.status == "clarify"
    assert result.topic is None


def test_topic_state_contains_rollback_fields():
    topic = _topic("topic-4", 0.9, "制造真实性")
    payload = topic.model_dump(mode="json")

    assert payload["claim_ids"] == ["claim-topic-4"]
    assert payload["metrics"] == ["authenticity_score"]
    assert payload["action"] == "analysis"
    assert payload["parent_topic_id"] is None
