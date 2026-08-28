"""服务层综合测试 — assessment 法律维度"""


def test_legal_deduction_constants():
    from app.services.assessment import EVENT_DEDUCTIONS, EVENT_LABELS
    assert EVENT_DEDUCTIONS["dishonesty"] == 30
    assert "tax_violation" in EVENT_LABELS


def test_calc_legal_score_no_events():
    from app.models.core_metrics import CoreMetrics
    from app.services.assessment import _calc_legal_score

    m = CoreMetrics(
        enterprise_id="x",
        display_label="广东·制造·小微",
        industry_l1="制造",
        industry_l2="其他未列明制造业",
        province="广东",
        city="深圳",
        scale_label="小微",
        credit_level="A",
        credit_score=80,
        tax_on_time_rate=0.9,
        tax_arrears_cnt=0,
        tax_violation_cnt=0,
        high_severity_cnt=0,
        is_dishonesty=False,
        is_execution=False,
        vat_revenue=100,
        invoice_revenue=100,
        finance_revenue=100,
        revenue_deviation=0.05,
        invoice_monthly_avg=50,
        social_trend="稳定",
        profit_margin=0.1,
        revenue_yoy=0.05,
        profit_yoy=0.05,
        debt_ratio=0.4,
        cash_flow_net=10,
        cash_flow_level="健康",
    )
    result = _calc_legal_score(m, [])
    assert result["score"] >= 60
    assert m.enterprise_name == "广东·制造·小微"


def test_calc_legal_score_tax_violation_deducts():
    from app.models.core_metrics import CoreMetrics
    from app.services.assessment import _calc_legal_score

    m = CoreMetrics(
        enterprise_id="x2",
        display_label="测试·制造·小微",
        industry_l1="制造",
        industry_l2="其他",
        province="广东",
        city="深圳",
        scale_label="小微",
        credit_level="C",
        credit_score=60,
        tax_on_time_rate=0.7,
        tax_arrears_cnt=1,
        tax_violation_cnt=2,
        high_severity_cnt=0,
        is_dishonesty=False,
        is_execution=False,
        vat_revenue=100,
        invoice_revenue=100,
        finance_revenue=100,
        revenue_deviation=0.1,
        invoice_monthly_avg=50,
        social_trend="稳定",
        profit_margin=0.1,
        revenue_yoy=0.05,
        profit_yoy=0.05,
        debt_ratio=0.4,
        cash_flow_net=10,
        cash_flow_level="健康",
    )
    result = _calc_legal_score(m, [])
    assert result["score"] < 80
    assert any("税务违法" in n["item"] for n in result["negative"])


def test_effective_weights_reduces_legal_partial():
    from app.services.assessment_weights import (
        DIMENSION_WEIGHTS,
        LEGAL_PARTIAL_COVERAGE_WEIGHT,
        effective_dimension_weights,
    )

    w = effective_dimension_weights("tax_illegal_only")
    assert w["legal"] == LEGAL_PARTIAL_COVERAGE_WEIGHT


def test_calc_legal_score_tax_audit_deducts():
    from datetime import datetime, timezone

    from app.models.core_metrics import CoreMetrics, LegalEvent
    from app.services.assessment import _calc_legal_score

    m = CoreMetrics(
        enterprise_id="x",
        display_label="广东·制造·小微",
        industry_l1="制造",
        industry_l2="其他",
        province="广东",
        city="深圳",
        scale_label="小微",
        credit_level="A",
        credit_score=80,
        tax_on_time_rate=0.9,
        tax_arrears_cnt=0,
        tax_violation_cnt=0,
        high_severity_cnt=0,
        is_dishonesty=False,
        is_execution=False,
        vat_revenue=100,
        invoice_revenue=100,
        finance_revenue=100,
        revenue_deviation=0.05,
        invoice_monthly_avg=50,
        social_trend="稳定",
        profit_margin=0.1,
        revenue_yoy=0.05,
        profit_yoy=0.05,
        debt_ratio=0.4,
        cash_flow_net=10,
        cash_flow_level="健康",
    )
    ev = LegalEvent(
        enterprise_id="x",
        event_type="tax_audit",
        severity="M",
        event_date=datetime.now(timezone.utc),
        description="税务稽查案件",
        source="syx_auditing",
        created_at=datetime.now(timezone.utc),
    )
    result = _calc_legal_score(m, [ev])
    assert result["score"] < 100
    assert any("稽查" in n.get("item", "") for n in result["negative"])
