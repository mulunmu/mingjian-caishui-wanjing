from __future__ import annotations

import pytest

from scripts.run_staging_primary_matrix import _ensure_primary_response, build_primary_query_plan


def test_primary_query_plan_covers_required_routes():
    plan = build_primary_query_plan([{"enterprise_id": "e1", "name": "企业1"}])
    categories = {item["category"] for item in plan}
    assert {
        "analysis",
        "greeting",
        "capability",
        "product_faq",
        "weather",
        "refusal",
        "abuse",
        "multilingual",
        "unknown_entity",
    }.issubset(categories)
    assert len(plan) >= 30
    assert len({item["query"] for item in plan}) == len(plan)


def test_analysis_case_rejects_clarify_as_incomplete():
    with pytest.raises(AssertionError, match="analysis is not answered"):
        _ensure_primary_response(
            {"category": "analysis"},
            {
                "reply": "请补充企业",
                "data": {"primary": {"status": "clarify", "fallback": False}},
            },
        )


def test_matrix_enforces_expected_route():
    with pytest.raises(AssertionError, match="expected route abuse"):
        _ensure_primary_response(
            {"category": "abuse"},
            {
                "reply": "回答",
                "data": {
                    "primary": {
                        "status": "answered",
                        "route": "capability",
                        "fallback": False,
                    }
                },
            },
        )
