from __future__ import annotations

from app.services.hallucination_guard import apply_chat_hallucination_guard
from app.services.metric_registry import (
    collapse_repeated_phrases,
    sanitize_surface_metric_tokens,
)


def test_known_internal_metric_tokens_are_replaced():
    text = "样本invoice_cnt均值 1477.7，tax_arrears_cnt均值 0.8。"
    cleaned = sanitize_surface_metric_tokens(text)
    assert "invoice_cnt" not in cleaned
    assert "tax_arrears_cnt" not in cleaned
    assert "开票张数" in cleaned
    assert "欠税次数" in cleaned


def test_repeated_chinese_phrase_is_collapsed():
    assert collapse_repeated_phrases("买卖买卖过于集中") == "买卖过于集中"


def test_chat_guard_cleans_internal_tokens_and_repetition():
    reply = "样本invoice_cnt偏高，买卖买卖过于集中。"
    cleaned, _, _ = apply_chat_hallucination_guard(reply, [], followups=[])
    assert "invoice_cnt" not in cleaned
    assert "买卖买卖" not in cleaned
    assert "开票张数" in cleaned
