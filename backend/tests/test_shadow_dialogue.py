from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.shadow_dialogue import build_shadow_dialogue
from tests.test_semantic_registry_seed import _engine


def test_shadow_dialogue_retrieves_validated_tools_only():
    engine = _engine()
    seed_semantic_registry(engine)
    with Session(engine) as session:
        result = build_shadow_dialogue(
            session,
            "企业17交税情况怎么样？",
            {
                "route": "analysis",
                "domain": "warn",
                "language": "zh",
                "entities": ["企业17"],
                "needs_tools": True,
                "needs_clarification": False,
            },
        )
    ids = [candidate.tool_id for candidate in result.candidates]
    assert "metric_tax_on_time_rate" in ids
    assert "scenario_tax_compliance" not in ids
    assert result.policy.retrieve_candidates is True
    assert result.policy.execute_tools is True


def test_shadow_dialogue_greeting_skips_tool_retrieval():
    engine = _engine()
    seed_semantic_registry(engine)
    with Session(engine) as session:
        result = build_shadow_dialogue(
            session,
            "你好",
            {
                "route": "greeting",
                "language": "zh",
                "entities": [],
                "needs_tools": False,
                "needs_clarification": False,
            },
        )
    assert result.candidates == []
    assert result.policy.retrieve_candidates is False


def test_candidate_probe_promotes_weak_route_with_explicit_entity():
    from sqlalchemy.orm import Session

    from app.services.shadow_dialogue import build_shadow_dialogue
    from app.services.semantic_registry_seed import seed_semantic_registry
    from tests.test_semantic_registry_seed import _engine

    engine = _engine()
    seed_semantic_registry(engine)
    with Session(engine) as session:
        result = build_shadow_dialogue(
            session,
            "企业2红字发票有多少",
            {
                "route": "capability",
                "domain": "general",
                "language": "zh",
                "entities": ["企业2"],
                "needs_tools": False,
                "needs_clarification": False,
            },
        )
    assert result.route.route == "analysis"
    assert result.policy.retrieve_candidates is True
    assert "metric_red_invoice_cnt" in [item.tool_id for item in result.candidates]