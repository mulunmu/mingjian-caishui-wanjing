from __future__ import annotations

from app.services.financial_model_eval import FINANCIAL_EVAL_CASES, score_financial_text


def test_financial_eval_accepts_causal_non_numeric_answer():
    case = FINANCIAL_EVAL_CASES[0]
    score = score_financial_text(case, "因为负债水平偏高，所以偿债缓冲更薄。")
    assert score["ok"] is True


def test_financial_eval_rejects_numbers_and_missing_causality():
    case = FINANCIAL_EVAL_CASES[0]
    score = score_financial_text(case, "负债率为 86。")
    assert "digit_leakage" in score["issues"]
    assert "missing_causal_connector" in score["issues"]
