"""评级展望（L1 规则层）：由风险等级 + 成长趋势统一决定，纯规则、可审计、可溯源。

铁律：展望只由 L0 数据 + L1 规则决定，不靠 LLM；趋势数据缺失时弃权（稳定），
不硬判「向好/恶化」这类没有数据支撑的结论。语气层只改表达，不改展望。
"""
from __future__ import annotations

from typing import Any

# 展望标签 → 语义色（与 _brand_tokens.css 语义色一致）
OUTLOOK_LABELS: dict[str, str] = {
    "正面": "#059669",
    "稳定": "#f57c00",
    "负面": "#dc2626",
}

# 高风险等级强制负面（展望的方向性只来自等级，不来自文本判断）
_NEGATIVE_LEVELS = {"高风险", "中高风险"}


def _to_float(value: Any) -> float | None:
    """趋势值转 float；缺失/非数值 → None（弃权，不硬判）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


def derive_outlook(
    *,
    risk_level: str,
    revenue_yoy: Any = None,
    profit_yoy: Any = None,
    high_severity_cnt: int = 0,
) -> dict[str, Any]:
    """推导评级展望，返回 {outlook, color}。

    规则（可审计、可回溯）：
      负面：high_severity_cnt > 0 或 risk_level ∈ {高风险, 中高风险}
      正面：risk_level == 低风险，或（revenue_yoy 与 profit_yoy 均有值且同时为正）
      稳定：其余（含趋势数据缺失时——弃权，不硬判）

    展望永远有值（由 risk_level 兜底），趋势缺失不产生空分析。
    """
    level = risk_level or ""

    if high_severity_cnt > 0 or level in _NEGATIVE_LEVELS:
        outlook = "负面"
    elif level == "低风险":
        outlook = "正面"
    else:
        ry = _to_float(revenue_yoy)
        py = _to_float(profit_yoy)
        if ry is not None and py is not None and ry > 0 and py > 0:
            outlook = "正面"
        else:
            outlook = "稳定"

    return {"outlook": outlook, "color": OUTLOOK_LABELS[outlook]}
