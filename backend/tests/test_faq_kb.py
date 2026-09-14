"""FAQ 收窄：能力范围问句不再命中 usage。"""
from __future__ import annotations

import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.faq_kb import build_faq_claims, build_methodology_claims, match_faq


def test_match_faq_keywords():
    # 「能做什么」归范围协商，不再 FAQ
    assert match_faq("这个系统能做什么") is None
    assert match_faq("我可以分析哪些企业") is None
    assert match_faq("数据怎么导入") is not None
    assert match_faq("报告怎么生成") is not None
    assert match_faq("综合评分怎么算的") is not None
    assert match_faq("随便一个无关问题zzz") is None


def test_match_faq_does_not_hijack_analysis_queries():
    assert match_faq("各地区数据怎么样") is None
    assert match_faq("营收数据可以对比吗") is None
    assert match_faq("报告覆盖了哪些维度") is None
    assert match_faq("分析各行业的趋势走向") is None
    assert match_faq("报告怎么生成") is not None
    assert match_faq("怎么导入数据") is not None or match_faq("数据怎么导入") is not None


def test_build_faq_claims_inventory_falls_to_fallback_text():
    """若误调 FAQ，能力问句走 fallback；路由层应走 negotiate_scope。"""
    claims, meta = build_faq_claims("这个系统能做什么")
    assert len(claims) == 1
    assert claims[0].value is None
    assert meta["faq_id"] == "fallback"


def test_match_faq_import_intent_has_action():
    entry = match_faq("我想导入数据")
    assert entry is not None
    assert entry["id"] == "data"
    claims, meta = build_faq_claims("我想导入数据")
    assert meta["faq_id"] == "data"
    assert meta["actions"][0]["target"] == "/ingest"
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
    assert re.search(r"\b\d", claims[0].claim) is None


def test_build_methodology_claims_all_value_none():
    claims, meta = build_methodology_claims()
    assert len(claims) > 0
    for c in claims:
        assert c.value is None
        assert c.trace.table == "metric_definition"
    assert meta["metric_keys"]


def test_build_methodology_specific_metric():
    claims, meta = build_methodology_claims(["credit_score"])
    assert len(claims) == 1
    assert claims[0].trace.field == "credit_score"
    assert claims[0].value is None
    assert meta["metric_keys"] == ["credit_score"]
