"""Deterministic scorer and cases for the optional financial review layer."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FinancialEvalCase:
    case_id: str
    claim: str
    metric: str
    number: float | None
    required_terms: tuple[str, ...]


FINANCIAL_EVAL_CASES: tuple[FinancialEvalCase, ...] = (
    FinancialEvalCase("leverage", "资产负债率均值明显偏高。", "debt_ratio", 0.86, ("负债", "偿债", "杠杆")),
    FinancialEvalCase("cashflow", "经营现金流净额为负。", "cash_flow_net", -100.0, ("现金流", "资金", "流动性")),
    FinancialEvalCase("net-margin", "净利率为负。", "net_margin", -0.05, ("盈利", "利润", "赚钱")),
    FinancialEvalCase("vat-burden", "增值税税负率偏低。", "vat_burden", 0.01, ("税负", "增值税", "税")),
    FinancialEvalCase("arrears", "存在欠税记录。", "tax_arrears_cnt", 2, ("欠税", "纳税", "合规")),
    FinancialEvalCase("red-invoice", "红字发票比例偏高。", "red_invoice_count_ratio", 0.28, ("红票", "红冲", "发票")),
    FinancialEvalCase("concentration", "客户集中度偏高。", "customer_concentration", 0.8, ("客户", "集中", "依赖")),
    FinancialEvalCase("supplier-hhi", "供应商HHI偏高。", "supplier_hhi", 0.6, ("供应商", "集中", "采购")),
    FinancialEvalCase("inventory", "存货周转率偏低。", "inventory_turnover", 1.0, ("存货", "周转", "库存")),
    FinancialEvalCase("cross-deviation", "多口径营收偏差偏高。", "cross_max_deviation", 0.5, ("营收", "口径", "偏差")),
)

_CAUSAL_MARKERS = ("因为", "因此", "所以", "意味着", "这表明", "说明", "导致", "反映")
_BANNED_AI_PHRASES = ("值得注意的是", "需要指出的是", "综上所述", "总而言之")


def score_financial_text(case: FinancialEvalCase, text: str | None) -> dict:
    value = (text or "").strip()
    issues: list[str] = []
    if not value:
        issues.append("empty")
    if re.search(r"\d", value):
        issues.append("digit_leakage")
    if any(marker in value for marker in _CAUSAL_MARKERS) is False:
        issues.append("missing_causal_connector")
    if any(term in value for term in case.required_terms) is False:
        issues.append("missing_required_concept")
    if any(phrase in value for phrase in _BANNED_AI_PHRASES):
        issues.append("banned_ai_phrase")
    return {"ok": not issues, "issues": issues, "text": value}
