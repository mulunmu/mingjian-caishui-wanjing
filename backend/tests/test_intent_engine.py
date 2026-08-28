"""意图识别 — 功能 × 维度切片"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.intent_engine import (
    _match_intent_rules,
    _normalize_intent,
    evaluate,
    extract_enterprises,
    is_followup_query,
    recognize,
)


def test_rule_trend_industry():
    r = recognize("分析各行业的趋势走向")
    assert r.function == "trend"
    assert r.dimension == "industry"


def test_rule_authenticity():
    intent, _ = _match_intent_rules("经营真实吗")
    assert intent == "authenticity"


def test_rule_benchmark():
    intent, _ = _match_intent_rules("跟同行比怎么样")
    assert intent == "benchmark"


def test_rule_signal():
    intent, _ = _match_intent_rules("有哪些风险预警")
    assert intent == "signal"


def test_rule_report():
    intent, _ = _match_intent_rules("生成评估报告")
    assert intent == "report"


def test_rule_email_report():
    intent, _ = _match_intent_rules("把报告发到我邮箱")
    assert intent == "email_report"


def test_rule_score():
    intent, _ = _match_intent_rules("分析税务健康")
    assert intent == "score"


def test_rule_general():
    intent, _ = _match_intent_rules("你好")
    assert intent == "general"


def test_extract_by_id_still_works():
    ids, names = extract_enterprises("查询ENT003的详情")
    assert "ENT003" in ids
    assert names == []


def test_extract_named_enterprise_returns_empty():
    ids, names = extract_enterprises("分析深圳明达科技的税务健康")
    assert ids == []
    assert names == []


def test_followup_detection():
    assert is_followup_query("它呢") is True
    assert is_followup_query("那税务方面呢") is True
    assert is_followup_query("分析行业趋势") is False


def test_followup_inherits_function():
    r = recognize("真实性呢", session_context={"last_function": "trend", "last_intent": "trend_industry"})
    assert r.function == "authenticity"
    r2 = recognize("那方面呢", session_context={"last_function": "trend"})
    assert r2.function == "trend"


def test_followup_switches_function_when_explicit():
    r = recognize("那舞弊方面呢", session_context={"last_function": "trend", "last_intent": "trend_industry"})
    assert r.function == "fraud"
    assert r.extras.get("switched_function") is True


def test_followup_inherits_province_from_session():
    from app.services import session_store

    sid = "persist-province-session"
    session_store.store_session(
        sid,
        intent="score_region",
        function="score",
        dimension="region",
        province="浙江",
        query="广东地区信用分",
    )
    ctx = session_store.get_session(sid) or {}
    r = recognize("那方面呢", session_context=ctx)
    assert r.province == "浙江"


def test_followup_switches_province_and_region_dim():
    ctx = {"last_function": "score", "last_intent": "score_region", "province": "浙江"}
    r = recognize("那广东呢", session_context=ctx)
    assert r.function == "score"
    assert r.province == "广东"
    assert r.dimension == "region"
    assert r.extras.get("switched_province") is True


def test_followup_switches_industry_and_industry_dim():
    ctx = {"last_function": "trend", "last_intent": "trend_industry", "industry_l1": "批发零售"}
    r = recognize("那制造呢", session_context=ctx)
    assert r.function == "trend"
    assert r.industry_l1 == "制造"
    assert r.dimension == "industry"
    assert r.extras.get("switched_industry") is True


def test_followup_keeps_function_when_only_province_changes():
    ctx = {"last_function": "signal", "last_intent": "signal_industry"}
    r = recognize("江苏呢", session_context=ctx)
    assert r.function == "signal"
    assert r.province == "江苏"


def test_evaluate_accuracy():
    result = evaluate()
    assert result["accuracy"] >= 80.0, f"Accuracy {result['accuracy']}% below 80%"


def test_signal_industry_distribution_keeps_industry_dim():
    r = recognize("各行业的风险分布")
    assert r.function == "signal"
    assert r.dimension == "industry"


def test_province_parsing():
    r = recognize("广东地区信用分对比")
    assert r.province == "广东"
    assert r.dimension == "region"


def test_industry_l1_options_includes_extended():
    from app.services.intent_engine import industry_l1_options

    opts = industry_l1_options()
    assert "新能源" in opts
    assert "医药" in opts


def test_it_substring_does_not_match_it_software():
    from app.services.intent_engine import _match_industry

    assert _match_industry("profit margin analysis") is None
    assert _match_industry("unit credit score") is None
    assert _match_industry("IT软件行业趋势") == "IT软件"
    assert _match_industry("it sector growth") == "IT软件"
