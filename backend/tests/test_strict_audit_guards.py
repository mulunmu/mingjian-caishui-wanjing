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


@pytest.mark.asyncio
async def test_chat_premium_locked_surfaces_message():
    """R1：PremiumReportLocked 在对话路径可见（须已订阅）。"""
    from app.services.chat_router import route_chat

    db = AsyncMock()
    subscriber = {"sub": "sub@example.com", "role": "user", "plan": "subscriber"}
    with patch("app.services.judgment_service.run_judgment", new_callable=AsyncMock) as run_j:
        run_j.return_value = ([], [], {})
        with patch(
            "app.services.slice_report.generate_slice_report",
            new_callable=AsyncMock,
            side_effect=PremiumReportLocked("custom"),
        ):
            with patch("app.services.conclusion_store.save_conclusion", return_value="c1"):
                with patch("app.services.conclusion_store.covered_functions", return_value=set()):
                    with patch("app.services.session_store.ensure_session_id", return_value="s1"):
                        with patch("app.services.session_store.store_session"):
                            with patch(
                                "app.services.llm_reply.generate_claim_reply",
                                new_callable=AsyncMock,
                                return_value=("ok", MagicMock(followups=[]), "template"),
                            ):
                                out = await route_chat(
                                    db, "生成综合尽调报告", session_id="s1", user=subscriber
                                )
    claims = out["data"]["claims"]
    assert any("付费" in (c.get("claim") or "") for c in claims)
    assert out["data"].get("slice", {}).get("report_locked") is True


@pytest.mark.asyncio
async def test_chat_custom_report_guides_not_generates():
    """定制化请求走引导分支：提示范围+场景，不直接产出报告（不再吞意图）。"""
    from app.services.chat_router import route_chat

    db = AsyncMock()
    subscriber = {"sub": "sub@example.com", "role": "user", "plan": "subscriber"}
    with patch(
        "app.services.intent_engine.recognize",
        return_value=MagicMock(
            function="report",
            dimension="overall",
            industry_l1=None,
            province=None,
            confidence=0.9,
            intent="report_overall",
            recipient=None,
            extras={},
        ),
    ):
        with patch("app.services.judgment_service.run_judgment", new_callable=AsyncMock) as run_j:
            run_j.return_value = ([], [], {})
            with patch("app.services.slice_report.generate_slice_report", new_callable=AsyncMock) as gen:
                with patch("app.services.conclusion_store.save_conclusion", return_value="c1"):
                    with patch("app.services.conclusion_store.covered_functions", return_value=set()):
                        with patch("app.services.session_store.ensure_session_id", return_value="s1"):
                            with patch("app.services.session_store.store_session"):
                                with patch(
                                    "app.services.llm_reply.generate_claim_reply",
                                    new_callable=AsyncMock,
                                    return_value=("ok", MagicMock(followups=[]), "template"),
                                ):
                                    out = await route_chat(db, "生成定制化的报告", session_id="s1", user=subscriber)
    gen.assert_not_called()
    claims = out["data"]["claims"]
    # 引导分支：二选一（固定模板 vs AI 定制），而非直接生成、也非「范围+场景」表单式追问
    assert any(("固定报告" in (c.get("claim") or "") and "定制报告" in (c.get("claim") or "")) for c in claims)
    # 引导动作：固定向导 + AI 定制两个入口
    actions = out["data"].get("actions") or []
    targets = [a.get("target") for a in actions]
    assert "/report?wizard=1" in targets
    assert "/?custom=1" in targets


@pytest.mark.asyncio
async def test_chat_email_report_attempts_send():
    """R2：email_report 读取 recipient 并尝试发信（收件人须匹配登录邮箱）。"""
    from app.services.chat_router import route_chat

    db = AsyncMock()
    subscriber = {"sub": "user@example.com", "role": "user", "plan": "subscriber"}
    biz_claim = Claim(
        claim="覆盖度 ok",
        value=ClaimValue(metric="coverage", number=1, unit="项"),
        trace=ClaimTrace(table="x", field="y", query_id="Q"),
        confidence="inferred",
    )

    async def _run_blocking(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch("app.services.judgment_service.run_judgment", new_callable=AsyncMock) as run_j:
        run_j.return_value = ([biz_claim], [], {})
        with patch(
            "app.services.slice_report.generate_slice_report",
            new_callable=AsyncMock,
            return_value=("rid", "/tmp/x.pdf", {"title": "报告", "chapters": [], "validation": {"ok": True}}),
        ):
            with patch("app.services.email_service.is_configured", return_value=True):
                with patch("app.services.email_service.send_slice_report") as send:
                    with patch("app.services.chat_router.run_blocking", side_effect=_run_blocking):
                        with patch("app.services.conclusion_store.save_conclusion", return_value="c1"):
                            with patch("app.services.conclusion_store.covered_functions", return_value=set()):
                                with patch("app.services.session_store.ensure_session_id", return_value="s1"):
                                    with patch("app.services.session_store.store_session"):
                                        with patch(
                                            "app.services.llm_reply.generate_claim_reply",
                                            new_callable=AsyncMock,
                                            return_value=("ok", MagicMock(followups=[]), "template"),
                                        ):
                                            with patch(
                                                "app.services.intent_engine.recognize",
                                                return_value=MagicMock(
                                                    function="email_report",
                                                    dimension="overall",
                                                    industry_l1=None,
                                                    province=None,
                                                    confidence=0.9,
                                                    intent="email_report_overall",
                                                    recipient="user@example.com",
                                                    extras={},
                                                ),
                                            ):
                                                await route_chat(
                                                    db,
                                                    "把报告发到 user@example.com",
                                                    session_id="s1",
                                                    user=subscriber,
                                                )
                    send.assert_called_once()


@pytest.mark.asyncio
async def test_chat_report_denied_without_subscription():
    """聊天生成报告须订阅；未登录不得绕过 /report 门槛。"""
    from app.services.chat_router import route_chat

    db = AsyncMock()
    with patch(
        "app.services.intent_engine.recognize",
        return_value=MagicMock(
            function="report",
            dimension="overall",
            industry_l1=None,
            province=None,
            confidence=0.9,
            intent="report_overall",
            recipient=None,
            extras={},
        ),
    ):
        with patch("app.services.judgment_service.run_judgment", new_callable=AsyncMock) as run_j:
            run_j.return_value = ([], [], {})
            with patch("app.services.slice_report.generate_slice_report", new_callable=AsyncMock) as gen:
                with patch("app.services.conclusion_store.save_conclusion", return_value="c1"):
                    with patch("app.services.conclusion_store.covered_functions", return_value=set()):
                        with patch("app.services.session_store.ensure_session_id", return_value="s1"):
                            with patch("app.services.session_store.store_session"):
                                with patch(
                                    "app.services.llm_reply.generate_claim_reply",
                                    new_callable=AsyncMock,
                                    return_value=("denied", MagicMock(followups=[]), "template"),
                                ):
                                    out = await route_chat(db, "生成行业趋势风控报告", session_id="s1")
    gen.assert_not_called()
    claims = out["data"]["claims"]
    assert any("登录" in (c.get("claim") or "") or "定制" in (c.get("claim") or "") for c in claims)
