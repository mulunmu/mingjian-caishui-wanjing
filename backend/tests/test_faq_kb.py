"""FAQ / 方法论：静态 KB，数字只走算法、不来自 LLM（value 一律 None）。"""
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.faq_kb import build_faq_claims, build_methodology_claims, match_faq


def test_match_faq_keywords():
    assert match_faq("这个系统能做什么") is not None
    assert match_faq("数据怎么导入") is not None
    assert match_faq("报告怎么生成") is not None
    assert match_faq("综合评分怎么算的") is not None
    assert match_faq("随便一个无关问题zzz") is None


def test_match_faq_does_not_hijack_analysis_queries():
    """裸词「数据/报告/功能」不得劫持研判问法（C1）。"""
    assert match_faq("各地区数据怎么样") is None
    assert match_faq("营收数据可以对比吗") is None
    assert match_faq("报告覆盖了哪些维度") is None
    assert match_faq("分析各行业的趋势走向") is None
    # 产品说明问句仍命中
    assert match_faq("报告怎么生成") is not None
    assert match_faq("怎么导入数据") is not None or match_faq("数据怎么导入") is not None


def test_build_faq_claims_has_no_numeric_value():
    claims, meta = build_faq_claims("这个系统能做什么")
    assert len(claims) == 1
    assert claims[0].value is None  # 无数字结论（不产生可被锚定的 number）
    assert claims[0].confidence == "inferred"
    assert meta["faq_id"] == "usage"
    assert claims[0].trace.table == "faq_kb"


def test_match_faq_import_intent_has_action():
    """「我想导入数据」这类祈使句要命中 data 条目并带引导动作（而非 fallback）。"""
    entry = match_faq("我想导入数据")
    assert entry is not None
    assert entry["id"] == "data"
    claims, meta = build_faq_claims("我想导入数据")
    assert meta["faq_id"] == "data"
    assert meta["actions"][0]["target"] == "/ingest"
    # 报告条目带「打开报告中心」动作
    _, report_meta = build_faq_claims("报告怎么生成")
    assert report_meta["actions"][0]["target"] == "/report"


def test_build_faq_fallback_no_value():
    claims, meta = build_faq_claims("zzz无关问题")
    assert claims[0].value is None
    assert meta["faq_id"] == "fallback"


def test_privacy_faq_mentions_redaction_without_digits():
    claims, meta = build_faq_claims("你们怎么保护企业名隐私")
    assert meta["faq_id"] == "privacy"
    assert claims[0].value is None
    assert "MD5" in claims[0].claim or "脱敏" in claims[0].claim
    # 静态回答不含独立数字（"MD5" 中的 5 不是数据数字，不应被误判）
    assert re.search(r"\b\d", claims[0].claim) is None


def test_build_methodology_claims_all_value_none():
    claims, meta = build_methodology_claims()
    assert len(claims) > 0
    for c in claims:
        assert c.value is None  # 口径解释不产生数值结论
        assert c.trace.table == "metric_definition"
    assert meta["metric_keys"]


def test_build_methodology_specific_metric():
    claims, meta = build_methodology_claims(["credit_score"])
    assert len(claims) == 1
    assert claims[0].trace.field == "credit_score"
    assert claims[0].value is None
    assert meta["metric_keys"] == ["credit_score"]
