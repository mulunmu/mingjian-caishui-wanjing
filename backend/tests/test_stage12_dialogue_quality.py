from __future__ import annotations

from scripts.run_stage12_dialogue_quality import build_dialogue_plan, validate_response


def _subject() -> dict[str, str]:
    return {"enterprise_id": "ENT001", "name": "企业1"}


def test_stage12_dialogue_plan_has_at_least_100_unique_cases():
    plan = build_dialogue_plan(_subject())
    keys = [(item["category"], item["query"]) for item in plan]

    assert len(plan) >= 100
    assert len(keys) == len(set(keys))
    assert {item["category"] for item in plan} >= {
        "analysis",
        "greeting",
        "capability",
        "product_faq",
        "out_of_domain",
        "refuse",
        "abuse",
        "multilingual",
        "unknown_entity",
        "clarify",
        "report",
    }


def test_stage12_validation_requires_analysis_claims():
    case = {"category": "analysis", "expected_status": {"answered"}, "expected_route": {"analysis"}}
    errors = validate_response(
        case,
        {
            "reply": "ok",
            "data": {
                "primary": {
                    "status": "answered",
                    "route": "analysis",
                    "fallback": False,
                },
                "claims": [],
            },
        },
    )

    assert "analysis_claims_empty" in errors


def test_stage12_validation_rejects_fallback():
    case = {"category": "greeting", "expected_status": {"answered"}, "expected_route": {"greeting"}}
    errors = validate_response(
        case,
        {
            "reply": "你好",
            "data": {
                "primary": {
                    "status": "answered",
                    "route": "greeting",
                    "fallback": True,
                }
            },
        },
    )

    assert any(item.startswith("unexpected_fallback") for item in errors)
