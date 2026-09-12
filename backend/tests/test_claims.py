"""claim schema + conclusion_store + llm 模板（无 LLM）"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.claim import Claim, ClaimTrace, ClaimValue, claims_to_public_reply, filter_claims
from app.services import conclusion_store
from app.services.llm_reply import _sanitize_conclusions, _template_from_claims


def test_filter_drops_asserted():
    claims = [
        Claim(claim="A", confidence="computed", value=ClaimValue(metric="a", number=1, unit="")),
        Claim(claim="B", confidence="inferred"),
        Claim(claim="C", confidence="asserted"),
    ]
    kept = filter_claims(claims)
    assert len(kept) == 2
    assert all(c.confidence != "asserted" for c in kept)


def test_public_reply_hides_evidence():
    claims = [
        Claim(
            claim="制造行业营收同比均值 5.2%。",
            value=ClaimValue(metric="avg_revenue_yoy", number=5.2, unit="%"),
            trace=ClaimTrace(table="core_metrics", field="revenue_yoy", query_id="Q1"),
            confidence="computed",
            evidence_chain=["raw=..."],
        )
    ]
    text = claims_to_public_reply(claims, followups=["看真实性"])
    assert "5.2" in text
    assert "evidence" not in text.lower()
    assert "core_metrics" not in text
    assert "看真实性" in text


def test_sanitize_blocks_new_numbers():
    claims = [
        Claim(
            claim="样本 10 家。",
            value=ClaimValue(metric="n", number=10, unit="家"),
            confidence="computed",
        )
    ]
    cleaned = _sanitize_conclusions(["样本 10 家。", "逾期率高达 99.9%。"], claims)
    assert cleaned == ["样本 10 家。"]


def test_sanitize_accepts_normalized_decimal_variants():
    """85.2 与 85.20 应视为同一锚点（hallucination_guard 归一化口径）。"""
    from app.services.llm_reply import _sanitize_narration

    claims = [
        Claim(
            claim="综合评分 85.2 分。",
            value=ClaimValue(metric="score", number=85.2, unit="分"),
            confidence="computed",
        )
    ]
    kept = _sanitize_narration("行业综合评分约 85.20 分，处于中等偏上水平。", claims)
    assert "85.20" in kept


def test_sanitize_drops_risk_direction_on_clean_chapter():
    """达标章（无风险结论）的解读段不得出现「承压/需核查」等风险措辞（claim 唯一化铁律）。"""
    from app.services.llm_reply import _sanitize_narration

    clean_claims = [
        Claim(
            claim="流动比率均值 1.80（达标，样本 1）。",
            value=ClaimValue(metric="current_ratio", number=1.8, unit=""),
            confidence="computed",
        )
    ]
    # 数字有锚点但结论方向矛盾（达标却说承压）→ 整句丢弃
    kept = _sanitize_narration("流动比率 1.80，偿债能力承压，需核查再融资。", clean_claims)
    assert "承压" not in kept
    assert "需核查" not in kept

    risk_claims = [
        Claim(
            claim="流动比率均值 0.90（预警，样本 1）。",
            value=ClaimValue(metric="current_ratio", number=0.9, unit=""),
            confidence="computed",
        )
    ]
    # 有风险结论 → 允许风险措辞
    kept_risk = _sanitize_narration("流动比率 0.90，短期偿债承压，需核查。", risk_claims)
    assert "承压" in kept_risk


def test_conclusion_store_roundtrip():
    claims = [
        Claim(
            claim="测试结论",
            value=ClaimValue(metric="x", number=1, unit=""),
            trace=ClaimTrace(table="core_metrics", field="credit_score", query_id="Q"),
            confidence="computed",
        )
    ]
    cid = conclusion_store.save_conclusion(
        session_id="sess-test",
        function="trend",
        dimension="industry",
        claims=claims,
        followups=["下一步"],
    )
    entry = conclusion_store.get_conclusion(cid)
    assert entry is not None
    assert entry["evidence_hidden"] is True
    assert entry["claims"][0]["trace"]["table"] == "core_metrics"
    assert "trend" in conclusion_store.covered_functions("sess-test")


def test_template_from_claims_prefix():
    claims = [Claim(claim="行业趋势平稳。", confidence="computed")]
    reply = _template_from_claims(claims, ["追问A"], with_prefix=True)
    assert reply.startswith("[规则模板生成]")
    assert "行业趋势平稳" in reply
