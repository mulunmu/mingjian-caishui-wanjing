"""A.4 约束解码契约：schema 句列表 + sanitize；发明数字必须被剥；不引 Outlines。"""
from __future__ import annotations

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.llm_reply import NarrationPlan, SummaryPlan, materialize_plan_sentences


def _clean_claims() -> list[Claim]:
    return [
        Claim(
            claim="流动比率均值 1.80（达标）。",
            confidence="computed",
            value=ClaimValue(metric="current_ratio", number=1.8, unit=""),
            trace=ClaimTrace(table="enterprise_financials", field="current_ratio", query_id="Q1"),
        )
    ]


def test_a4_materialize_keeps_anchored_sentences():
    text = materialize_plan_sentences(
        ["流动比率 1.80，偿债能力稳健", "建议维持现有融资结构"],
        _clean_claims(),
    )
    assert text is not None
    assert "1.80" in text
    assert "稳健" in text


def test_a4_materialize_drops_invented_numbers_and_risk_on_clean():
    text = materialize_plan_sentences(
        ["流动比率 1.80，偿债能力承压", "逾期率高达 99.9%"],
        _clean_claims(),
    )
    # 承压 + 99.9 均应被剥；若全丢则弃权 None
    assert text is None or ("99.9" not in text and "承压" not in text)


def test_a4_plan_schema_bounds():
    p = NarrationPlan(sentences=["a", "b", "c"])
    assert len(p.sentences) == 3
    s = SummaryPlan(sentences=["x"] * 6)
    assert len(s.sentences) == 6
