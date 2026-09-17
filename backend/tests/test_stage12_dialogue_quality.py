from __future__ import annotations

from scripts.run_stage12_dialogue_quality import build_dialogue_plan, validate_response
from scripts import run_stage12_dialogue_quality as quality


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


def test_report_case_auto_confirms_langgraph_approval(monkeypatch):
    calls = []

    def fake_request(method, url, *, body=None, token=None, timeout=120):
        calls.append(body)
        if len(calls) == 1:
            return (
                200,
                {
                    "reply": "报告生成需要确认",
                    "data": {
                        "primary": {
                            "status": "clarify",
                            "route": "report",
                            "fallback": False,
                            "approval_required": True,
                        }
                    },
                },
                10.0,
            )
        return (
            200,
            {
                "reply": "报告已生成",
                "data": {
                    "primary": {
                        "status": "answered",
                        "route": "report",
                        "fallback": False,
                    },
                    "report": {"report_id": "report-1"},
                },
            },
            20.0,
        )

    monkeypatch.setattr(quality, "BASE_URL", "http://test")
    monkeypatch.setattr(quality, "_request", fake_request)
    result = quality._run_case(
        "token",
        {
            "id": "D103",
            "index": 103,
            "category": "report",
            "query": "生成评级报告",
            "enterprise_id": "ENT001",
            "expected_status": {"answered"},
            "expected_route": {"report"},
        },
    )
    assert result["ok"] is True
    assert calls[1]["query"] == "确认生成报告"
