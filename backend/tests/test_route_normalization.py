from __future__ import annotations

from app.services.route_normalize import normalize_route


def test_explicit_company_number_is_extracted_even_if_model_omits_it():
    route = normalize_route(
        {
            "route": "analysis",
            "domain": "loan",
            "language": "zh",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
        },
        "企业17能不能贷款？",
    )
    assert route.entities == ["企业17"]
    assert route.needs_clarification is False


def test_report_route_normalizes_to_report_domain():
    route = normalize_route(
        {
            "route": "report",
            "domain": "report",
            "language": "zh",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
        },
        "请生成一份财务健康报告",
    )
    assert route.route == "report"
    assert route.domain == "report"


def test_foreign_analysis_normalizes_to_language_switch():
    route = normalize_route(
        {
            "route": "analysis",
            "domain": "warn",
            "language": "en",
            "entities": ["company 17"],
            "needs_tools": True,
            "needs_clarification": False,
        },
        "Hello, can you check company 17 tax risk?",
    )
    assert route.route == "language_switch"
    assert route.entities == ["company 17"]


def test_missing_subject_requires_clarification():
    route = normalize_route(
        {
            "route": "analysis",
            "domain": "rating",
            "language": "zh",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
        },
        "公司稳不稳？",
    )
    assert route.needs_clarification is True


def test_named_company_phrase_is_extracted():
    route = normalize_route(
        {
            "route": "analysis",
            "domain": "rating",
            "language": "zh",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
        },
        "腾讯这家公司怎么样？",
    )
    assert route.entities == ["腾讯"]
