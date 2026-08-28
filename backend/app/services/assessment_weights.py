# 五维评估权重：税务25 / 经营25 / 行业20 / 法律15 / 财务15

DIMENSION_WEIGHTS: dict[str, float] = {
    "tax_health": 0.25,
    "authenticity": 0.25,
    "industry": 0.20,
    "legal": 0.15,
    "finance": 0.15,
}

# 法律维仅税务侧覆盖时，降低其在综合分中的权重（避免恒 100 分拉高总分）
LEGAL_PARTIAL_COVERAGE_WEIGHT = 0.05


def effective_dimension_weights(legal_coverage: str | None = None) -> dict[str, float]:
    """tax_illegal_only 时将法律维 15% → 5%，差额按比例分给其余四维。"""
    weights = dict(DIMENSION_WEIGHTS)
    if legal_coverage != "tax_illegal_only":
        return weights
    spare = weights["legal"] - LEGAL_PARTIAL_COVERAGE_WEIGHT
    weights["legal"] = LEGAL_PARTIAL_COVERAGE_WEIGHT
    others = [k for k in weights if k != "legal"]
    share = spare / len(others)
    for k in others:
        weights[k] = round(weights[k] + share, 6)
    return weights

DIMENSION_LABELS: dict[str, str] = {
    "tax_health": "税务健康",
    "authenticity": "经营真实性",
    "industry": "行业地位",
    "legal": "法律合规",
    "finance": "财务健康",
}

FINROBOT_REPORT_SECTIONS = [
    "Executive Summary",
    "Company Overview",
    "Financial Analysis",
    "Industry Positioning",
    "Risk Assessment",
    "Valuation & Outlook",
    "Appendix: Data Sources",
]
