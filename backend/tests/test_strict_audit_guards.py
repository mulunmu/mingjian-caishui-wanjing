"""严格审计缺陷回归：C1/R1/R2/C3 集成边界"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.judgment_service import (
    build_session_synthesis_claims,
    is_synthesis_claim_dict,
    without_synthesis_claims,
)
from app.services.report_templates import PremiumReportLocked


def _analysis_act_patch():
    from app.services.dialog_act import DialogAct

    return patch(
        "app.services.dialog_act.classify",
        new_callable=AsyncMock,
        return_value=DialogAct(act="analyze", confidence=1.0),
    )


def test_synthesis_roundtrip_headline_not_polluted():
    """C1：synthesis 不入库时，下轮 headline 仍是业务 claim。"""
    from app.services import conclusion_store

    sid = "strict-synth-roundtrip"
    synth = Claim(
        claim="会话综合风控分析（已覆盖 2 维）：趋势：制造同比 5%。",
        value=ClaimValue(metric="session_synthesis_dims", number=2, unit="维"),
        trace=ClaimTrace(table="conclusion_store", field="function", query_id="Q_session_synthesis"),
        confidence="inferred",
    )
    biz = Claim(
        claim="制造行业同比 5%。",
        value=ClaimValue(metric="yoy", number=5, unit="%"),
        trace=ClaimTrace(table="core_metrics", field="revenue_yoy", query_id="Q_trend"),
        confidence="computed",
    )
    conclusion_store.save_conclusion(
        session_id=sid,
        function="trend",
        dimension="industry",
        claims=without_synthesis_claims([synth, biz]),
        followups=[],
    )
    conclusion_store.save_conclusion(
        session_id=sid,
        function="signal",
        dimension="signal",
        claims=[
            Claim(
                claim="样本 3 家存在预警信号。",
                value=ClaimValue(metric="n", number=3, unit="家"),
                trace=ClaimTrace(table="core_metrics", field="credit_level", query_id="Q_sig"),
                confidence="computed",
            )
        ],
        followups=[],
    )
    claims, meta = build_session_synthesis_claims(sid)
    assert meta.get("synthesis_functions")
    stored = conclusion_store.list_session_conclusions(sid)
    trend_claims = next(i["claims"] for i in stored if i["function"] == "trend")
    assert not any(is_synthesis_claim_dict(c) for c in trend_claims)
    assert "会话综合风控分析" not in trend_claims[0]["claim"]


def test_benford_insufficient_sample_wording():
    """C3：样本不足不说「未显著违例」。"""
    from app.services.judgment_service import _claim
    from app.services.authenticity_engine import analyze_authenticity_batch
    from unittest.mock import MagicMock

    metrics = [
        MagicMock(
            enterprise_id=f"e{i}",
            display_label=f"样本{i}",
            vat_revenue=1000 * (i + 1),
            invoice_revenue=1000 * (i + 1),
            finance_revenue=1000 * (i + 1),
            revenue_deviation=0.05,
            social_trend="稳定",
        )
        for i in range(5)
    ]
    out = analyze_authenticity_batch(metrics, industry_l1="制造")
    bf = out.get("benford") or {}
    conformity = bf.get("conformity")
    if conformity == "insufficient_sample":
        verdict = "样本不足、未检验"
    elif bf.get("violation"):
        verdict = "违例"
    else:
        verdict = "未显著违例"
    assert verdict == "样本不足、未检验"
    assert "未显著违例" not in f"结论{verdict}"


def test_benford_no_industry_uses_slice_not_snapshot():
    """无行业时 Benford 用本切片主体金额，绝不复用全库 snapshot（n 应为切片主体数）。"""
    from app.services.authenticity_engine import analyze_authenticity_batch

    metrics = [
        MagicMock(
            enterprise_id=f"e{i}",
            display_label=f"样本{i}",
            vat_revenue=1000 * (i + 1),
            invoice_revenue=1000 * (i + 1),
            finance_revenue=1000 * (i + 1),
            revenue_deviation=0.05,
            social_trend="稳定",
        )
        for i in range(40)
    ]
    out = analyze_authenticity_batch(metrics, industry_l1=None)
    assert out["benford_source"] == "slice_metrics"
    assert out["benford_scope"] == "本切片"
    bf = out.get("benford") or {}
    # n 等于切片主体数（40），而非全库快照（16478）
    assert bf.get("n") == 40


def test_benford_small_slice_abstains_not_snapshot():
    """切片 <30 家时弃权（insufficient_sample），不硬凑全库数字。"""
    from app.services.authenticity_engine import analyze_authenticity_batch

    metrics = [
        MagicMock(
            enterprise_id=f"e{i}",
            display_label=f"样本{i}",
            vat_revenue=1000 * (i + 1),
            invoice_revenue=1000 * (i + 1),
            finance_revenue=1000 * (i + 1),
            revenue_deviation=0.05,
            social_trend="稳定",
        )
        for i in range(5)
    ]
    out = analyze_authenticity_batch(metrics, industry_l1=None)
    bf = out.get("benford") or {}
    assert bf.get("conformity") == "insufficient_sample"
    assert bf.get("chi2") is None
    assert out["benford_source"] == "slice_metrics"
