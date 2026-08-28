"""个体报告「财务分析」章：三大报表 + 四能力比率（弃权优先，评级对齐洞察引擎）"""
import sys
import os
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.core_metrics import CoreMetrics, IndustryBenchmark
from app.models.financials import EnterpriseFinancials
from app.services.slice_report import _financial_chapter


def _cm(has_statements: bool, industry: str = "制造") -> CoreMetrics:
    return CoreMetrics(
        enterprise_id="e1",
        display_label="广东·制造·小微",
        industry_l1=industry,
        industry_l2="其他",
        province="广东",
        city="深圳",
        has_financial_statements=has_statements,
    )


def _fin(**overrides) -> EnterpriseFinancials:
    return EnterpriseFinancials(enterprise_id="e1", **overrides)


class _FakeDb:
    def __init__(self, fin=None, cm=None, bench=None):
        self._fin = fin
        self._cm = cm
        self._bench = bench

    async def get(self, model, key):
        if model is EnterpriseFinancials:
            return self._fin
        if model is CoreMetrics:
            return self._cm
        if model is IndustryBenchmark:
            return self._bench
        return None


@pytest.mark.asyncio
async def test_financial_chapter_builds_when_statements_present():
    fin = _fin(
        debt_ratio=Decimal("0.78"),
        current_ratio=Decimal("1.8"),
        gross_margin=Decimal("0.25"),
        revenue=Decimal("1000000"),
        net_profit=Decimal("100000"),
    )
    cm = _cm(True)
    bench = IndustryBenchmark(
        industry_l1="制造",
        avg_debt_ratio=Decimal("0.6"),
        avg_gross_margin=Decimal("0.2"),
    )
    result = await _financial_chapter(_FakeDb(fin, cm, bench), enterprise_id="e1")

    assert result is not None
    chapter, _claims = result
    assert chapter["title"] == "财务分析"
    # 客观评级：资产负债率 78% → 预警
    assert chapter["meta"]["ratio_ratings"]["debt_ratio"] == "预警"
    assert chapter["meta"]["ratio_ratings"]["gross_margin"] == "达标"
    # 三大报表 numeric_rows 覆盖资产/利润/现金流
    labels = [r[0] for r in chapter["numeric_rows"]]
    assert "资产总计" in labels
    assert "净利润" in labels
    assert "经营活动现金流量净额" in labels
    # 每条结论 traceable 到 enterprise_financials
    for c in chapter["claims"]:
        assert c["trace"]["table"] == "enterprise_financials"
    # 对标柱状图（本样本 vs 行业均值）
    assert chapter["charts"]["type"] == "bar"
    assert "本样本" in [s["name"] for s in chapter["charts"]["data"]["series"]]


@pytest.mark.asyncio
async def test_financial_chapter_none_without_statements():
    fin = _fin()
    cm = _cm(False)  # has_financial_statements=False → 弃权
    assert await _financial_chapter(_FakeDb(fin, cm, None), enterprise_id="e1") is None
    # 无 financials 记录 → 弃权
    assert await _financial_chapter(_FakeDb(None, cm, None), enterprise_id="e1") is None


@pytest.mark.asyncio
async def test_financial_chapter_ratio_zero_is_abstain():
    fin = _fin(debt_ratio=Decimal("0"))  # 0=弃权
    result = await _financial_chapter(_FakeDb(fin, _cm(True), None), enterprise_id="e1")
    chapter, _claims = result
    assert chapter["meta"]["ratio_ratings"]["debt_ratio"] == "无数据"
    debt_claim = next(c for c in chapter["claims"] if "资产负债率" in c["claim"])
    assert "无数据" in debt_claim["claim"]
    assert debt_claim["value"] is None  # 弃权不伪造数字


def test_financial_benchmarks_assess_and_format():
    from app.services.financial_benchmarks import (
        assess_financial_ratio,
        format_financial_ratio,
        FINANCIAL_GROUPS,
        FINANCIAL_RATIOS,
    )

    assert assess_financial_ratio("debt_ratio", Decimal("0.78")) == "预警"
    assert assess_financial_ratio("debt_ratio", Decimal("0.5")) == "达标"
    assert assess_financial_ratio("debt_ratio", Decimal("0")) == "无数据"
    assert assess_financial_ratio("current_ratio", Decimal("0.5")) == "预警"
    assert assess_financial_ratio("current_ratio", Decimal("1.8")) == "达标"

    assert format_financial_ratio("debt_ratio", Decimal("0.78")) == "78.0%"
    assert format_financial_ratio("current_ratio", Decimal("1.85")) == "1.85"
    assert format_financial_ratio("debt_ratio", Decimal("0")) == "无数据"

    # 四能力分组齐全，比率覆盖四组
    assert FINANCIAL_GROUPS == ["偿债能力", "营运能力", "盈利能力", "成长能力"]
    groups = {FINANCIAL_RATIOS[f]["group"] for f in FINANCIAL_RATIOS}
    assert groups == set(FINANCIAL_GROUPS)


def test_dupont_breakdown_complete():
    from app.services.financial_benchmarks import dupont_breakdown

    # roe = net_margin × asset_turnover × equity_multiplier = 0.05 × 2.0 × 2.0 = 0.20
    d = dupont_breakdown(
        net_margin=Decimal("0.05"),
        asset_turnover=Decimal("2.0"),
        total_assets=Decimal("1000"),
        owner_equity=Decimal("500"),
        roe=Decimal("0.20"),
    )
    assert d["complete"] is True
    assert d["roe"] == 0.2
    vals = {f["field"]: f["value"] for f in d["factors"]}
    assert vals["net_margin"] == 0.05
    assert vals["asset_turnover"] == 2.0
    assert vals["equity_multiplier"] == 2.0
    # 展示：净利率 5.0%、周转率 2.00、权益乘数 2.00
    assert d["factors"][0]["disp"] == "5.0%"
    assert d["factors"][1]["disp"] == "2.00"
    assert d["factors"][2]["disp"] == "2.00"


def test_dupont_breakdown_abstain_negative_equity():
    from app.services.financial_benchmarks import dupont_breakdown

    d = dupont_breakdown(
        net_margin=Decimal("0.05"),
        asset_turnover=Decimal("2.0"),
        total_assets=Decimal("1000"),
        owner_equity=Decimal("-500"),  # 权益为负 → 权益乘数无定义
        roe=Decimal("0"),
    )
    assert d["complete"] is False
    em = next(f for f in d["factors"] if f["field"] == "equity_multiplier")
    assert em["value"] is None
    assert em["disp"] is None


def test_dupont_breakdown_abstain_zero_margin():
    from app.services.financial_benchmarks import dupont_breakdown

    d = dupont_breakdown(
        net_margin=Decimal("0"),  # 0=弃权
        asset_turnover=Decimal("2.0"),
        total_assets=Decimal("1000"),
        owner_equity=Decimal("500"),
        roe=Decimal("0"),
    )
    assert d["complete"] is False
    nm = next(f for f in d["factors"] if f["field"] == "net_margin")
    assert nm["value"] is None
