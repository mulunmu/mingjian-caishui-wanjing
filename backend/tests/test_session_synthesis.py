"""Benford 行业切片 + 会话综合风控分析"""
import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.authenticity_engine import analyze_authenticity_batch
from app.services.judgment_service import build_session_synthesis_claims


def test_benford_uses_industry_slice_when_industry_set():
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
    out = analyze_authenticity_batch(metrics, industry_l1="制造")
    assert out["benford_source"].startswith("slice_metrics")
    assert out["benford_scope"] == "本切片"


def test_session_synthesis_requires_two_functions():
    from app.services import conclusion_store

    sid = "test-synth-session"
    conclusion_store.save_conclusion(
        session_id=sid,
        function="trend",
        dimension="industry",
        claims=[
            Claim(
                claim="制造行业同比 5%。",
                value=ClaimValue(metric="yoy", number=5, unit="%"),
                trace=ClaimTrace(table="core_metrics", field="revenue_yoy", query_id="Q1"),
                confidence="computed",
            )
        ],
        followups=[],
    )
    claims, meta = build_session_synthesis_claims(
        sid,
        pending_function="signal",
        pending_claims=[
            Claim(
                claim="样本 10 家存在预警信号。",
                value=ClaimValue(metric="n", number=10, unit="家"),
                trace=ClaimTrace(table="core_metrics", field="credit_level", query_id="Q2"),
                confidence="computed",
            )
        ],
    )
    assert len(claims) == 1
    assert meta.get("synthesis_functions") == ["signal", "trend"]


def test_session_overall_judgment_when_three_functions():
    from app.services import conclusion_store

    sid = "test-overall-session"
    for fn, text in (
        ("trend", "制造行业同比 5%。"),
        ("score", "全样本均分 47 分。"),
        ("signal", "样本 10 家存在预警信号。"),
    ):
        conclusion_store.save_conclusion(
            session_id=sid,
            function=fn,
            dimension="overall",
            claims=[
                Claim(
                    claim=text,
                    value=ClaimValue(metric="m", number=1, unit=""),
                    trace=ClaimTrace(table="core_metrics", field="x", query_id="Q"),
                    confidence="computed",
                )
            ],
            followups=[],
        )
    claims, meta = build_session_synthesis_claims(sid)
    assert len(claims) == 2
    assert meta.get("overall_judgment") is True
    assert "会话级综合判断" in claims[1].claim


def test_synthesis_claims_are_detected():
    from app.services.judgment_service import is_synthesis_claim, without_synthesis_claims

    synth = Claim(
        claim="会话综合风控分析（已覆盖 2 维）：趋势：…",
        value=ClaimValue(metric="session_synthesis_dims", number=2, unit="维"),
        trace=ClaimTrace(table="conclusion_store", field="function", query_id="Q_session_synthesis"),
        confidence="inferred",
    )
    biz = Claim(
        claim="制造行业同比 5%。",
        value=ClaimValue(metric="yoy", number=5, unit="%"),
        trace=ClaimTrace(table="core_metrics", field="revenue_yoy", query_id="Q1"),
        confidence="computed",
    )
    assert is_synthesis_claim(synth) is True
    assert is_synthesis_claim(biz) is False
    assert len(without_synthesis_claims([synth, biz])) == 1
