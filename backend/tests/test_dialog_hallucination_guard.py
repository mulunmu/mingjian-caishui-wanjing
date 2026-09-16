"""对话路径 hallucination_guard 回归测试（P3 验收）。

铁律：对话终态 reply 中每个数字必须与 Claim 锚定，否则被剥离。
"""
from __future__ import annotations

import re

from app.schemas.claim import Claim, ClaimValue, filter_claims
from app.services.hallucination_guard import (
    apply_chat_hallucination_guard,
    collect_allowed_numbers,
    filter_unanchored_sentences,
    sentence_has_anchor,
)


def _make_claims() -> list[Claim]:
    """制造一组带数字的 Claim 作为唯一事实源。"""
    return [
        Claim(
            claim="综合风险得分 72 分，中等风险",
            value=ClaimValue(metric="overall_score", number=72, unit="分"),
            confidence="computed",
        ),
        Claim(
            claim="纳税准时率 85%，低于行业均值 95%",
            value=ClaimValue(metric="tax_on_time_rate", number=0.85, unit=""),
            confidence="computed",
        ),
    ]


class TestDialogHallucinationGuard:
    """对话终态 hallucination_guard 回归。"""

    def test_allowed_numbers_from_claims(self):
        claims = _make_claims()
        kept = filter_claims(claims)
        allowed = collect_allowed_numbers(kept)
        assert "72" in allowed
        assert "85" in allowed or "0.85" in allowed
        assert "95" in allowed

    def test_anchored_sentence_passes(self):
        claims = _make_claims()
        kept = filter_claims(claims)
        allowed = collect_allowed_numbers(kept)
        assert sentence_has_anchor("综合风险得分 72 分，处于中等水平。", allowed)

    def test_unanchored_number_stripped(self):
        claims = _make_claims()
        kept = filter_claims(claims)
        sentences = [
            "综合风险得分 72 分，中等风险。",
            "利润率仅 15%，远低于行业均值 30%。",
        ]
        kept_sents, dropped = filter_unanchored_sentences(sentences, kept)
        assert len(dropped) == 1
        assert "15%" in dropped[0] or "30%" in dropped[0]
        assert len(kept_sents) == 1
        assert "72" in kept_sents[0]

    def test_no_number_sentence_passes(self):
        claims = _make_claims()
        kept = filter_claims(claims)
        sentences = [
            "该企业整体风险处于中等水平。",
            "建议关注税务合规和现金流管理。",
        ]
        kept_sents, dropped = filter_unanchored_sentences(sentences, kept)
        assert len(dropped) == 0
        assert len(kept_sents) == 2

    def test_fabricated_number_in_reply_stripped(self):
        claims = _make_claims()
        kept = filter_claims(claims)
        reply_sentences = [
            "综合风险得分 72 分，处于中等风险水平。",
            "利润率仅 42%，偿债能力承压。",
            "建议关注税务合规。",
        ]
        kept_sents, dropped = filter_unanchored_sentences(reply_sentences, kept)
        assert len(dropped) >= 1
        assert any("42" in d for d in dropped)
        assert any("72" in s for s in kept_sents)
        assert any("税务合规" in s for s in kept_sents)

    def test_followup_with_unanchored_number_filtered(self):
        claims = _make_claims()
        kept = filter_claims(claims)
        allowed = collect_allowed_numbers(kept)
        followups = [
            "查看利润率 42% 的原因",
            "对比同行业信用分",
            "综合分 72 的详细拆解",
        ]
        filtered = [
            fu for fu in followups
            if not re.search(r"\d", fu) or any(num in fu for num in allowed)
        ]
        assert len(filtered) == 2
        assert all("42" not in f for f in filtered)

    def test_apply_guard_rewrites_hint_and_followups(self):
        """统一闸门：reply / report_hint / followups 一并过闸。"""
        claims = _make_claims()
        reply = "综合风险得分 72 分。利润率 42% 很差。"
        hint = "覆盖度 99% 时可导出报告。"
        fus = ["综合分 72 拆解", "看利润率 42%"]
        new_reply, new_hint, new_fus = apply_chat_hallucination_guard(
            reply, claims, report_hint=hint, followups=fus
        )
        assert "72" in new_reply
        assert "42" not in new_reply
        assert new_hint is None or "99" not in (new_hint or "")
        assert all("42" not in f for f in new_fus)
        assert any("72" in f for f in new_fus)

    def test_empty_allowed_strips_all_digits(self):
        """空 allowed（无数字 Claim）：剥离一切含数字句子。"""
        reply = "该企业稳健。营收 1000 万看起来不错。"
        new_reply, _, fus = apply_chat_hallucination_guard(
            reply, [], report_hint=None, followups=["看营收 1000"]
        )
        assert "1000" not in new_reply
        assert "稳健" in new_reply
        assert fus == []
