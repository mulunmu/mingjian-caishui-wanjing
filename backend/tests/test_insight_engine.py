"""洞察引擎单元测试：确定性规则 + 可溯源 claim。"""
import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.core_metrics import CoreMetrics
from app.models.engine_store import EnterpriseEngineFeatures
from app.services.insight_engine import (
    evaluate_insights,
    insights_to_claims,
)


def _metrics(**overrides) -> CoreMetrics:
    base = dict(
        enterprise_id="ent_test_001",
        display_label="测试·行业A·小微",
        industry_l1="行业A",
        industry_l2="细分",
        province="浙江",
        city="杭州",
        credit_level="A",
        credit_score=Decimal("85"),
        tax_on_time_rate=Decimal("0.95"),
        tax_arrears_cnt=0,
        tax_violation_cnt=0,
        high_severity_cnt=0,
        is_dishonesty=False,
        is_execution=False,
        loan_cnt=0,
        loan_amount=Decimal("0"),
        vat_revenue=Decimal("0"),
        invoice_revenue=Decimal("0"),
        finance_revenue=Decimal("0"),
        revenue_deviation=Decimal("0.10"),
        invoice_monthly_avg=0,
        invoice_cnt=100,
        red_invoice_cnt=0,
        social_trend="稳定",
        social_months=12,
        profit_margin=Decimal("0.20"),
        revenue_yoy=Decimal("0.05"),
        profit_yoy=Decimal("0.05"),
        debt_ratio=Decimal("0.50"),
        cash_flow_net=Decimal("100000"),
        cash_flow_level="健康",
    )
    base.update(overrides)
    return CoreMetrics(**base)


def _features(**overrides) -> EnterpriseEngineFeatures:
    base = dict(
        enterprise_id="ent_test_001",
        fraud_composite_score=Decimal("10"),
        fraud_risk_level="低风险",
        fraud_signals="[]",
        scbm_mismatch_score=Decimal("0"),
        red_invoice_score=Decimal("0"),
        concentration_score=Decimal("0"),
        sequence_gap_ratio=Decimal("0"),
        pyod_score=Decimal("0"),
        authenticity_score=Decimal("80"),
        cross_avg_deviation=Decimal("0.05"),
        cross_suspicious=False,
        invoice_cnt=100,
    )
    base.update(overrides)
    return EnterpriseEngineFeatures(**base)


def _ids(insights):
    return [i.rule_id for i in insights]


def test_clean_enterprise_no_insight():
    assert evaluate_insights(_metrics(), _features()) == []


def test_finance_rules():
    ins = evaluate_insights(_metrics(debt_ratio=Decimal("0.85")), None)
    assert "F-01" in _ids(ins)

    ins = evaluate_insights(_metrics(cash_flow_net=Decimal("-50000")), None)
    assert "F-02" in _ids(ins)

    ins = evaluate_insights(_metrics(revenue_yoy=Decimal("0.20"), profit_margin=Decimal("0.02")), None)
    assert "F-03" in _ids(ins)

    ins = evaluate_insights(_metrics(revenue_yoy=Decimal("-0.30")), None)
    assert "F-04" in _ids(ins)


def test_tax_rules():
    ins = evaluate_insights(_metrics(tax_arrears_cnt=2), None)
    assert "T-01" in _ids(ins)
    assert any(i.severity == "高危" for i in ins if i.rule_id == "T-01")

    ins = evaluate_insights(_metrics(tax_violation_cnt=1), None)
    assert "T-02" in _ids(ins)

    ins = evaluate_insights(_metrics(credit_level="D"), None)
    assert "T-03" in _ids(ins)

    ins = evaluate_insights(_metrics(tax_on_time_rate=Decimal("0.60")), None)
    assert "T-04" in _ids(ins)


def test_zero_sentinel_abstains():
    """缺失比率（0 哨兵）不得触发 T-04 / F-03 / F-01。"""
    assert "T-04" not in _ids(evaluate_insights(_metrics(tax_on_time_rate=Decimal("0")), None))
    assert "F-03" not in _ids(
        evaluate_insights(_metrics(revenue_yoy=Decimal("0.20"), profit_margin=Decimal("0")), None)
    )
    assert "F-01" not in _ids(evaluate_insights(_metrics(debt_ratio=Decimal("0")), None))
    # 0.75 介于旧扣分阈值 0.85 与评级阈值 0.7 之间，统一后应预警
    assert "F-01" in _ids(evaluate_insights(_metrics(debt_ratio=Decimal("0.75")), None))


def test_fraud_rules_use_signals():
    ins = evaluate_insights(_metrics(), _features(fraud_signals='["scbm_mismatch"]', scbm_mismatch_score=Decimal("80")))
    assert "I-01" in _ids(ins)

    ins = evaluate_insights(_metrics(), _features(fraud_signals='["red_invoice"]', red_invoice_score=Decimal("60")))
    assert "I-02" in _ids(ins)

    # 红冲无信号但占比高也应命中
    ins = evaluate_insights(_metrics(red_invoice_cnt=20, invoice_cnt=100), _features())
    assert "I-02" in _ids(ins)

    ins = evaluate_insights(_metrics(), _features(fraud_signals='["concentration"]', concentration_score=Decimal("70")))
    assert "I-03" in _ids(ins)

    ins = evaluate_insights(_metrics(), _features(fraud_signals='["sequence_gap"]', sequence_gap_ratio=Decimal("0.4")))
    assert "I-04" in _ids(ins)

    ins = evaluate_insights(_metrics(), _features(fraud_risk_level="高风险", fraud_composite_score=Decimal("85")))
    assert "I-05" in _ids(ins)


def test_fraud_missing_features_skips():
    # features 为 None 时弃权，不编造
    ins = evaluate_insights(_metrics(), None)
    assert not any(i.rule_id.startswith("I-") for i in ins)


def test_tax_new_rules():
    ins = evaluate_insights(_metrics(tax_late_penalty_cnt=1), None)
    assert "T-05" in _ids(ins)

    ins = evaluate_insights(_metrics(correction_times=80), None)
    assert "T-06" in _ids(ins)

    ins = evaluate_insights(_metrics(vat_burden=Decimal("0.003")), None)
    assert "T-07" in _ids(ins)

    ins = evaluate_insights(_metrics(income_tax_burden=Decimal("0.0005")), None)
    assert "T-08" in _ids(ins)

    # 阈值边界：低于触发值不命中；税负为 0（弃权）不误判
    assert evaluate_insights(_metrics(correction_times=79), None) == []
    assert evaluate_insights(_metrics(vat_burden=Decimal("0.006")), None) == []
    assert evaluate_insights(_metrics(vat_burden=Decimal("0")), None) == []


def test_invoice_new_rules():
    ins = evaluate_insights(_metrics(customer_concentration=Decimal("0.6")), None)
    assert "I-06" in _ids(ins)

    ins = evaluate_insights(_metrics(supplier_concentration=Decimal("0.6")), None)
    assert "I-07" in _ids(ins)

    ins = evaluate_insights(
        _metrics(customer_concentration=Decimal("0.6"), supplier_concentration=Decimal("0.6")), None,
    )
    assert "I-08" in _ids(ins)
    i08 = next(i for i in ins if i.rule_id == "I-08")
    assert i08.severity == "高危"

    ins = evaluate_insights(_metrics(category_concentration=Decimal("0.95")), None)
    assert "I-09" in _ids(ins)

    # 边界：≤0.5 不命中；双边集中需两端同时超 0.5
    assert evaluate_insights(_metrics(customer_concentration=Decimal("0.5")), None) == []
    ins = evaluate_insights(
        _metrics(customer_concentration=Decimal("0.6"), supplier_concentration=Decimal("0.4")), None,
    )
    assert "I-06" in _ids(ins) and "I-08" not in _ids(ins)


def test_invoice_void_price_rules():
    # I-10 作废发票占比 >15%
    ins = evaluate_insights(_metrics(void_invoice_cnt=20, invoice_cnt=100), None)
    assert "I-10" in _ids(ins)
    # 边界：≤15% 不命中；无开票（弃权）不误判
    assert "I-10" not in _ids(evaluate_insights(_metrics(void_invoice_cnt=15, invoice_cnt=100), None))
    assert "I-10" not in _ids(evaluate_insights(_metrics(void_invoice_cnt=5, invoice_cnt=0), None))

    # I-11 单价离散 >100000
    ins = evaluate_insights(_metrics(unit_price_ratio=Decimal("150000")), None)
    assert "I-11" in _ids(ins)
    assert "I-11" not in _ids(evaluate_insights(_metrics(unit_price_ratio=Decimal("100000")), None))


def test_change_frequent_rule():
    # T-10 变更登记 ≥15
    ins = evaluate_insights(_metrics(change_cnt=15), None)
    assert "T-10" in _ids(ins)
    assert "T-10" not in _ids(evaluate_insights(_metrics(change_cnt=14), None))


def test_authenticity_rules():
    ins = evaluate_insights(_metrics(revenue_deviation=Decimal("0.40")), None)
    assert "A-01" in _ids(ins)

    ins = evaluate_insights(_metrics(), _features(cross_suspicious=True))
    assert "A-02" in _ids(ins)

    ins = evaluate_insights(_metrics(), _features(authenticity_score=Decimal("20")))
    assert "A-03" in _ids(ins)


def test_legal_rules():
    ins = evaluate_insights(_metrics(is_dishonesty=True), None)
    assert "R-01" in _ids(ins)
    assert any(i.severity == "高危" for i in ins if i.rule_id == "R-01")

    ins = evaluate_insights(_metrics(is_execution=True), None)
    assert "R-02" in _ids(ins)


def test_multiple_high_risk_stacks_r03():
    ins = evaluate_insights(
        _metrics(tax_arrears_cnt=1, is_dishonesty=True),
        _features(fraud_signals='["scbm_mismatch"]', scbm_mismatch_score=Decimal("80")),
    )
    assert "R-03" in _ids(ins)
    r03 = next(i for i in ins if i.rule_id == "R-03")
    assert r03.severity == "高危"
    # 用户可见面不得露出 rule_id（T-01/A-02 等）
    fact = r03.fact_text()
    assert "T-01" not in fact
    assert "A-02" not in fact
    assert "R-01" not in fact
    assert "存在欠税" in fact or "失信" in fact or "叠加" in fact


def test_insights_to_claims_traceable():
    ins = evaluate_insights(_metrics(debt_ratio=Decimal("0.85"), is_dishonesty=True), None)
    claims = insights_to_claims(ins, "ent_test", "测试")
    assert len(claims) == len(ins)
    for c in claims:
        assert c.confidence == "computed"
        # 每条 claim 必须可溯源（含 bool 主证据的司法规则）
        assert c.trace is not None and c.trace.table
    # 数字须能从 claim 文本或 value 找到锚点
    f01 = next(c for c in claims if (c.value and c.value.metric == "F-01"))
    assert f01.value is not None
    assert f01.value.number == 85.0  # 0.85 → 85.0%
