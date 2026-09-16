from __future__ import annotations

import pytest

from scripts.run_staging_composition_matrix import (
    build_composition_query_plan,
    validate_composition_response,
)


def test_composition_query_plan_has_thirty_distinct_cases():
    plan = build_composition_query_plan({"enterprise_id": "e1", "name": "企业1"})
    assert len(plan) == 30
    assert len({item["query"] for item in plan}) == 30


def test_composition_response_requires_plan_and_claims():
    with pytest.raises(AssertionError, match="composition plan missing"):
        validate_composition_response(
            {"query": "q"},
            {"data": {"primary": {"fallback": False}, "claims": []}},
        )
