"""评估层新增「发票健康」维度 + 税务画像补强信号 单元测试"""
import sys
import os
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.core_metrics import CoreMetrics


def _m(eid="e1", **overrides) -> CoreMetrics:
    base = dict(
        enterprise_id=eid,
        display_label="广东·制造·小微",
        industry_l1="制造",
        industry_l2="其他",
        province="广东",
        city="深圳",
        scale_label="小微",
        credit_score=Decimal("80"),
        tax_on_time_rate=Decimal("0.9"),
        customer_concentration=Decimal("0"),
        supplier_concentration=Decimal("0"),
        category_concentration=Decimal("0"),
        void_invoice_cnt=0,
        unit_price_ratio=Decimal("0"),
        invoice_cnt=0,
    )
    base.update(overrides)
    return CoreMetrics(**base)


def test_calc_invoice_all_abstain_returns_neutral():
    from app.services.assessment import _calc_invoice

    m = _m()
    r = _calc_invoice(m, [m])
    assert r["score"] == 50.0
    assert r["engine"] == "invoice_concentration"
    assert r["note"] == "集中度全弃权"


def test_calc_invoice_high_concentration_lower_score():
    from app.services.assessment import _calc_invoice

    # 高集中度 → 分散度分位低 → 得分低；低集中度反之
    high = _m("high", customer_concentration=Decimal("0.9"),
              supplier_concentration=Decimal("0.9"),
              category_concentration=Decimal("0.9"))
    low = _m("low", customer_concentration=Decimal("0.1"),
             supplier_concentration=Decimal("0.1"),
             category_concentration=Decimal("0.1"))
    pop = [high, low]
    r_high = _calc_invoice(high, pop)
    r_low = _calc_invoice(low, pop)
    assert r_high["score"] < 50.0
    assert r_low["score"] > 50.0
    assert r_high["score"] < r_low["score"]


def test_calc_invoice_void_and_price_deductions():
    from app.services.assessment import _calc_invoice

    m = _m(customer_concentration=Decimal("0.1"),
           supplier_concentration=Decimal("0.1"),
           category_concentration=Decimal("0.1"),
           invoice_cnt=100, void_invoice_cnt=20,
           unit_price_ratio=Decimal("200000"))
    r = _calc_invoice(m, [m])
    items = [n["item"] for n in r["negative"]]
    assert "作废发票占比异常" in items
    assert "单价离散异常" in items


def test_calc_tax_health_profile_signals():
    from app.services.assessment import _calc_tax_health

    score, pos, neg = _calc_tax_health(
        _m(tax_late_penalty_cnt=2, correction_times=80,
           vat_burden=Decimal("0.003"), income_tax_burden=Decimal("0.0005"),
           change_cnt=15)
    )
    items = [n["item"] for n in neg]
    assert "滞纳金/罚款" in items
    assert "申报更正异常频繁" in items
    assert "增值税税负率明显偏低" in items
    assert "所得税税负率明显偏低" in items
    assert "变更登记频繁" in items


def test_calc_tax_health_no_false_positive_on_zero():
    from app.services.assessment import _calc_tax_health

    # 全部为 0（弃权）时不得误判税负偏低
    _, _, neg = _calc_tax_health(_m())
    items = [n["item"] for n in neg]
    assert "增值税税负率明显偏低" not in items
    assert "所得税税负率明显偏低" not in items


def test_calc_tax_health_abstains_zero_on_time_rate():
    """tax_on_time_rate=0 弃权：不计准时率贡献，与洞察 T-04 对齐。"""
    from app.services.assessment import _calc_tax_health

    score_present, pos_present, _ = _calc_tax_health(_m(tax_on_time_rate=Decimal("0.9")))
    score_zero, pos_zero, _ = _calc_tax_health(_m(tax_on_time_rate=Decimal("0")))
    labels_zero = [p["item"] for p in pos_zero]
    assert "纳税准时率（数据弃权）" in labels_zero
    assert any(p["item"] == "纳税准时率" for p in pos_present)
    # 有准时率时应高于弃权（同信用分）
    assert score_present > score_zero


def test_industry_profile_stats_skips_abstain():
    from app.services.assessment import _industry_profile_stats

    a = _m("a", customer_concentration=Decimal("0.3"), vat_burden=Decimal("0.02"))
    b = _m("b", customer_concentration=Decimal("0"), vat_burden=Decimal("0.01"))
    stats = _industry_profile_stats([a, b])

    assert len(stats) == 1
    row = stats[0]
    assert row["industry_l1"] == "制造"
    assert row["n"] == 2
    # 弃权（0）被剔除：客户集中度均值只算非 0 样本 → 0.3
    assert row["customer_concentration"] == pytest.approx(0.3)
    assert row["vat_burden"] == pytest.approx(0.015)


def test_industry_profile_stats_null_when_all_abstain():
    from app.services.assessment import _industry_profile_stats

    a = _m("a", vat_burden=Decimal("0"))
    b = _m("b", vat_burden=Decimal("0"))
    stats = _industry_profile_stats([a, b])

    # 全弃权 → None，展示层渲染「暂无数据」而非 0
    assert stats[0]["vat_burden"] is None


def test_dimension_weights_sum_to_one_and_include_invoice():
    from app.services.assessment_weights import DIMENSION_WEIGHTS, DIMENSION_LABELS

    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.01
    assert "invoice" in DIMENSION_WEIGHTS
    assert DIMENSION_LABELS["invoice"] == "发票健康"
