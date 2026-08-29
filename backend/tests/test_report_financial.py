"""个体报告「财务深度分析」：杜邦分解 + 同业对标柱状图（弃权优先，评级对齐洞察引擎）"""
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.core_metrics import IndustryBenchmark
from app.models.financials import EnterpriseFinancials
from app.services.slice_report import _build_benchmark_chart, _build_dupont


def _fin(**overrides) -> EnterpriseFinancials:
    return EnterpriseFinancials(enterprise_id="e1", **overrides)


def test_dupont_builds_when_statements_present():
    fin = _fin(
        net_margin=Decimal("0.05"),
        asset_turnover=Decimal("2.0"),
        total_assets=Decimal("1000"),
        owner_equity=Decimal("500"),
        roe=Decimal("0.20"),
    )
    d = _build_dupont(fin, True)
    assert d is not None
    assert d["complete"] is True
    assert d["roe_disp"] == "20.0%"
    # 三因子 traceable：净利率 / 总资产周转率 / 权益乘数
    vals = {f["field"]: f["value"] for f in d["factors"]}
    assert vals["net_margin"] == 0.05
    assert vals["asset_turnover"] == 2.0
    assert vals["equity_multiplier"] == 2.0


def test_dupont_none_without_statements():
    # 无报表 / has_financial_statements=False → 弃权，不硬凑
    assert _build_dupont(None, False) is None
    assert _build_dupont(_fin(), False) is None


def test_benchmark_chart_builds():
    fin = _fin(
        debt_ratio=Decimal("0.78"),
        gross_margin=Decimal("0.25"),
        net_margin=Decimal("0.10"),
        roe=Decimal("0.15"),
        roa=Decimal("0.08"),
    )
    bench = IndustryBenchmark(
        industry_l1="制造",
        avg_debt_ratio=Decimal("0.6"),
        avg_gross_margin=Decimal("0.2"),
        avg_net_margin=Decimal("0.08"),
        avg_roe=Decimal("0.12"),
        avg_roa=Decimal("0.06"),
    )
    chart = _build_benchmark_chart(fin, True, bench)
    assert chart is not None
    assert chart["type"] == "bar"
    assert "资产负债率" in chart["data"]["labels"]
    assert [s["name"] for s in chart["data"]["series"]] == ["行业均值", "本样本"]
    # 本样本值 ×100（0.78 → 78.0）
    own_series = next(s for s in chart["data"]["series"] if s["name"] == "本样本")
    assert own_series["values"][0] == 78.0


def test_benchmark_chart_abstain_without_bench_or_zero():
    fin = _fin(debt_ratio=Decimal("0.78"), gross_margin=Decimal("0.25"))
    # 无行业基准 → 弃权
    assert _build_benchmark_chart(fin, True, None) is None
    # 无报表 → 弃权
    assert _build_benchmark_chart(None, False, IndustryBenchmark(industry_l1="制造")) is None
    # 比率全 0 → 弃权（不伪造对标）
    assert _build_benchmark_chart(_fin(), True, IndustryBenchmark(industry_l1="制造")) is None


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
