"""四层字段映射引擎（阶段二）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.services.field_mapping import map_columns, map_columns_with_llm, normalize


def test_normalize():
    assert normalize(" 信用_分 ") == "信用分"
    assert normalize("Credit Score") == "creditscore"
    assert normalize("营收(同比)") == "营收同比"
    assert normalize("") == ""


def test_map_columns_exact():
    res = map_columns(["信用分", "营业收入"])
    by = {r["source_column"]: r for r in res}
    assert by["信用分"]["target_field"] == "credit_score"
    assert by["信用分"]["tier"] == "exact"
    assert by["信用分"]["confidence"] == 100
    assert by["营业收入"]["target_field"] == "finance_revenue"


def test_map_columns_fuzzy():
    res = map_columns(["营收同比增长"])
    r = res[0]
    assert r["target_field"] == "revenue_yoy"
    assert r["tier"] == "fuzzy"
    assert r["needs_review"] is True


def test_map_columns_unmatched():
    res = map_columns(["完全无关的列xyz"])
    assert res[0]["target_field"] is None
    assert res[0]["tier"] == "unmatched"
    assert res[0]["needs_review"] is True


def test_map_columns_saved_priority():
    saved = {normalize("我的信用分"): "credit_score"}
    res = map_columns(["我的信用分"], saved=saved)
    assert res[0]["tier"] == "saved"
    assert res[0]["target_field"] == "credit_score"
    assert res[0]["confidence"] == 100


@pytest.mark.asyncio
async def test_map_columns_with_llm_degrades_without_llm():
    """LLM 未配置时，四层映射退化为纯三层，不阻塞接入。"""
    res = await map_columns_with_llm(["信用分", "完全无关的列xyz"])
    by = {r["source_column"]: r for r in res}
    assert by["信用分"]["target_field"] == "credit_score"
    assert by["完全无关的列xyz"]["tier"] == "unmatched"
