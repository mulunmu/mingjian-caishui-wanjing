"""个体报告「财务深度分析」：杜邦分解 + 同业对标柱状图（弃权优先，评级对齐洞察引擎）"""
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.core_metrics import IndustryBenchmark
from app.models.financials import EnterpriseFinancials
from app.services.slice_report import (
    _build_benchmark_chart,
    _build_dimension_sections,
    _build_dupont,
    _build_statements,
    _collect_advantages,
    _collect_advice,
)


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


# ── 空数据消除（铁律：0=弃权，无值不出现；不写「无数据/—」占位） ──


def test_dimension_sections_empty_without_statements():
    # 无报表 → 弃权不出现（整段分维度不出现）
    assert _build_dimension_sections(None, False) == []
    # 有报表但全 0 → 同样弃权不出现
    assert _build_dimension_sections(_fin(), True) == []


def test_dimension_sections_drop_zero_and_no_placeholder():
    fin = _fin(
        debt_ratio=Decimal("0.78"),        # 预警
        current_ratio=Decimal("1.8"),      # 达标
        quick_ratio=Decimal("0"),          # 无值 → 不出现
        gross_margin=Decimal("0.25"),      # 达标
        net_margin=Decimal("0.10"),        # 达标
        roe=Decimal("0.15"),               # 达标
        roa=Decimal("0"),                  # 仅展示 → 无值不出现
        receivables_turnover=Decimal("3.0"),
        inventory_turnover=Decimal("3.0"),
        asset_turnover=Decimal("2.0"),     # 仅展示，有值出现
        revenue_yoy=Decimal("0.05"),       # 达标
        profit_yoy=Decimal("0"),           # 仅展示 → 无值不出现
        operating_cf=Decimal("1000"),      # 达标
        investing_cf=Decimal("0"),         # 无值 → 不出现
        financing_cf=Decimal("-200"),      # 仅展示，有值出现
        total_assets=Decimal("1000"),
        total_liab=Decimal("600"),
        owner_equity=Decimal("400"),
    )
    dims = _build_dimension_sections(fin, True)
    by_key = {d["key"]: d for d in dims}
    assert set(by_key) == {
        "capital_structure", "solvency", "profitability",
        "cashflow", "operation", "growth",
    }
    # 无值指标不出现
    assert [m["label"] for m in by_key["solvency"]["metrics"]] == ["流动比率"]  # quick_ratio 剔除
    profit_labels = [m["label"] for m in by_key["profitability"]["metrics"]]
    assert "总资产收益率" not in profit_labels  # roa=0 剔除
    cf_labels = [m["label"] for m in by_key["cashflow"]["metrics"]]
    assert "投资活动现金流量净额" not in cf_labels  # investing_cf=0 剔除
    growth_labels = [m["label"] for m in by_key["growth"]["metrics"]]
    assert "净利润同比" not in growth_labels  # profit_yoy=0 剔除
    # 无「无数据/—」占位评级
    for d in dims:
        for m in d["metrics"]:
            assert m["rating"] in ("达标", "预警", "")
            assert m["rating"] != "无数据"
            assert m["standard"] != "—"


def test_statements_none_without_fin():
    assert _build_statements(None, False) is None


def test_statements_zero_rows_show_placeholder():
    """零值行显式输出【暂无可用数据】，禁止空白单元格。"""
    fin = _fin(revenue=Decimal("1000"), cost=Decimal("0"), net_profit=Decimal("100"))
    st = _build_statements(fin, True)
    rows = {r[0]: r[1] for r in st["income"]["rows"]}
    assert "营业收入" in rows
    assert rows["营业成本"] == "【暂无可用数据】"
    assert "净利润" in rows


def test_collect_advantages_and_advice_no_placeholder():
    # 空 → 返回 []，不再写「未识别到显著优势项」/「建议结合同业基准」占位
    assert _collect_advantages({"credit_level": "C"}, None) == []
    assert _collect_advice([]) == []
