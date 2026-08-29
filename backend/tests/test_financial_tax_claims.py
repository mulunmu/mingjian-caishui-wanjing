"""聚合财务/税务 builder：四能力评级 + 税负/欠税，0=弃权，阈值统一（铁律 L1）"""
import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _row(**kw):
    return MagicMock(**kw)


# FINANCIAL_RATIOS 全部字段（缺省 0=弃权）
_FIN_FIELDS = {
    "debt_ratio": 0.0,
    "current_ratio": 0.0,
    "quick_ratio": 0.0,
    "receivables_turnover": 0.0,
    "inventory_turnover": 0.0,
    "asset_turnover": 0.0,
    "gross_margin": 0.0,
    "net_margin": 0.0,
    "roe": 0.0,
    "roa": 0.0,
    "revenue_yoy": 0.0,
    "profit_yoy": 0.0,
}

_TAX_FIELDS = {
    "tax_on_time_rate": 0.0,
    "vat_burden": 0.0,
    "income_tax_burden": 0.0,
    "tax_arrears_cnt": 0,
    "tax_violation_cnt": 0,
    "tax_late_penalty_cnt": 0,
}


def _fin_row(has_fin=1, **overrides):
    kw = dict(_FIN_FIELDS)
    kw.update(overrides)
    kw["has_financial_statements"] = has_fin
    return _row(**kw)


def _tax_row(**overrides):
    kw = dict(_TAX_FIELDS)
    kw.update(overrides)
    return _row(**kw)


@pytest.mark.asyncio
async def test_financial_claims_rates_rating_and_abstain(monkeypatch):
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _fin_row(debt_ratio=0.8, gross_margin=0.3, receivables_turnover=3.0,
                     current_ratio=1.6, revenue_yoy=0.1),
            _fin_row(debt_ratio=0.4, gross_margin=0.15, receivables_turnover=2.5,
                     current_ratio=1.8, revenue_yoy=0.2),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    claims, meta = await judgment_service.build_financial_claims(None)

    metrics = {c.value.metric: c for c in claims if c.value and c.value.number is not None}
    # 覆盖率 claim
    assert metrics["financial_coverage"].value.number == 2

    # 资产负债率均值 0.6（> 0.7 才预警）→ 达标；毛利率均值 0.225 → 达标
    gm = metrics["gross_margin"]
    assert "达标" in gm.claim
    assert gm.value.number == pytest.approx(22.5)  # is_pct ×100

    # 弃权字段（inventory_turnover=0）不产 claim
    assert "inventory_turnover" not in metrics

    assert meta["charts"]["type"] == "bar"
    assert meta["financial_coverage"] == 2


@pytest.mark.asyncio
async def test_financial_claims_warn_on_debt_ratio(monkeypatch):
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [_fin_row(debt_ratio=0.78)]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    claims, _meta = await judgment_service.build_financial_claims(None)
    debt = next(c for c in claims if c.value and c.value.metric == "debt_ratio")
    assert "预警" in debt.claim
    assert debt.value.number == pytest.approx(78.0)


@pytest.mark.asyncio
async def test_financial_claims_all_zero_abstain(monkeypatch):
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [_fin_row(has_fin=1)]  # 有报表但比率全 0=弃权

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    claims, meta = await judgment_service.build_financial_claims(None)
    # 仅覆盖率 claim，无任何比率 claim（0=弃权，不产假结论）
    assert len(claims) == 1
    assert claims[0].value.metric == "financial_coverage"
    assert meta["charts"] is None


@pytest.mark.asyncio
async def test_trend_growth_shrink_from_revenue_yoy_sign(monkeypatch):
    """趋势「增长/缩减」由 revenue_yoy 符号计数，与方向字段同源（不再用 social_trend）。"""
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _row(industry_l1="制造", revenue_yoy=0.05, social_trend="稳定"),
            _row(industry_l1="制造", revenue_yoy=0.03, social_trend=None),
            _row(industry_l1="服务", revenue_yoy=-0.04, social_trend="稳定"),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    claims, meta = await judgment_service.build_trend_industry_claims(None)
    by_ind = {i["industry_l1"]: i for i in meta["industries"]}
    assert by_ind["制造"]["grow_cnt"] == 2
    assert by_ind["制造"]["shrink_cnt"] == 0
    assert by_ind["服务"]["grow_cnt"] == 0
    assert by_ind["服务"]["shrink_cnt"] == 1
    # 文案与字段同源表述
    assert any("营收增长" in c.claim for c in claims)


@pytest.mark.asyncio
async def test_tax_claims_on_time_burden_and_counts(monkeypatch):
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _tax_row(tax_on_time_rate=0.9, vat_burden=0.03, income_tax_burden=0.02,
                     tax_arrears_cnt=1, tax_late_penalty_cnt=2),
            _tax_row(tax_on_time_rate=0.7, vat_burden=0.05, income_tax_burden=0.01,
                     tax_violation_cnt=1),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    claims, meta = await judgment_service.build_tax_claims(None)

    on_time = next(c for c in claims if c.value and c.value.metric == "tax_on_time_rate")
    assert on_time.value.number == pytest.approx(80.0)  # (0.9+0.7)/2 ×100
    arrears = next(c for c in claims if c.value and c.value.metric == "tax_arrears_cnt")
    assert arrears.value.number == 1
    assert meta["violation_cnt"] == 1
    assert meta["late_penalty_cnt"] == 2
    assert meta["charts"]["type"] == "bar"


def test_scenario_chapters_use_aggregate_builders():
    from app.services.report_templates import get_scenario

    fin_first = get_scenario("financial")["chapters"][0]
    assert fin_first["function"] == "financial"
    tax_first = get_scenario("tax")["chapters"][0]
    assert tax_first["function"] == "tax"


def test_analysis_functions_include_financial_tax():
    from app.services.judgment_service import ANALYSIS_FUNCTIONS

    assert {"financial", "tax"} <= ANALYSIS_FUNCTIONS
