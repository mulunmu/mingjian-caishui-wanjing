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


def test_chinese_entity_number_is_normalized():
    route = normalize_route(
        {
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
        },
        "企业一有哪些值得分析的点？",
    )
    assert route.entities == ["企业1"]


def test_compound_chinese_entity_number_is_normalized():
    route = normalize_route(
        {
            "route": "analysis",
            "domain": "warn",
            "language": "zh",
            "entities": [],
            "needs_tools": True,
            "needs_clarification": False,
        },
        "企业二十三的税务风险怎么样？",
    )
    assert route.entities == ["企业23"]


def test_analysis_action_routes_to_cohort_analysis_without_keyword_inference():
    route = normalize_route(
        {
            "route": "capability",
            "action": "analysis",
            "language": "zh",
            "entities": [],
        },
        "当前数据按行业是怎么划分的？有哪些行业供我们分析？",
    )
    assert route.route == "analysis"
    assert route.domain == "general"
    assert route.needs_clarification is False


def test_metadata_action_overrides_industry_words():
    route = normalize_route(
        {
            "route": "analysis",
            "action": "metadata_query",
            "route_hint": "analysis",
            "language": "zh",
            "entities": [],
        },
        "行业有哪些？",
    )
    assert route.route == "inventory"


def test_report_action_overrides_legacy_analysis_route():
    route = normalize_route(
        {
            "route": "analysis",
            "action": "report",
            "route_hint": "analysis",
            "language": "zh",
            "entities": [],
        },
        "帮我生成报告",
    )
    assert route.route == "report"
    assert route.domain == "report"


def test_missing_action_does_not_run_semantic_keyword_override():
    route = normalize_route(
        {"route": "capability", "language": "zh", "entities": []},
        "行业有哪些？",
    )
    assert route.route == "capability"


def test_explicit_inventory_route_is_not_overridden_by_industry_words():
    route = normalize_route(
        {
            "route": "inventory",
            "language": "zh",
            "entities": [],
            "filters": {},
            "needs_tools": False,
            "needs_clarification": False,
        },
        "行业有哪些？",
    )
    assert route.route == "inventory"


def test_cohort_scenario_questions_do_not_require_enterprise():
    for query, domain in (
        ("哪里信号最多？", "warn"),
        ("哪里可疑要查？", "audit"),
        ("按行业拆风险等级", "rating"),
    ):
        route = normalize_route(
            {"route": "analysis", "domain": domain, "language": "zh", "entities": []},
            query,
        )
        assert route.needs_clarification is False
