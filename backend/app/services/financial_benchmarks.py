"""财务四能力比率阈值口径（对齐洞察引擎 F-01~F-10 与《报告设计规范》§5.2）。

客观评级三态：达标 / 预警 / 无数据（0=弃权）。铁律：评级由本表统一决定，与场景无关；
语气层只改表达，不改评级。比率口径 0-1（is_pct=True 展示 ×100），周转率/流动比率为倍数。
"""
from __future__ import annotations

from typing import Any

# 四能力分组顺序（偿债 → 营运 → 盈利 → 成长）
FINANCIAL_GROUPS: list[str] = ["偿债能力", "营运能力", "盈利能力", "成长能力"]

# field → 配置。is_pct=True 表示存 0-1、展示 ×100；False 为倍数（流动/速动/周转率）。
# warn_dir: "gt"=高于阈值预警 / "lt"=低于阈值预警；None=仅展示不评级（如 roa/asset_turnover）。
FINANCIAL_RATIOS: dict[str, dict[str, Any]] = {
    # ── 偿债能力 ──
    "debt_ratio": {
        "group": "偿债能力", "label": "资产负债率", "unit": "%", "is_pct": True,
        "warn_dir": "gt", "warn_threshold": 0.7, "good_threshold": 0.7,
        "rule_id": "F-01",
    },
    "current_ratio": {
        "group": "偿债能力", "label": "流动比率", "unit": "", "is_pct": False,
        "warn_dir": "lt", "warn_threshold": 1.0, "good_threshold": 1.5,
        "rule_id": "F-05",
    },
    "quick_ratio": {
        "group": "偿债能力", "label": "速动比率", "unit": "", "is_pct": False,
        "warn_dir": "lt", "warn_threshold": 0.5, "good_threshold": 1.0,
        "rule_id": "F-06",
    },
    # ── 营运能力 ──
    "receivables_turnover": {
        "group": "营运能力", "label": "应收账款周转率", "unit": "次/年", "is_pct": False,
        "warn_dir": "lt", "warn_threshold": 2.0, "good_threshold": 2.0,
        "rule_id": "F-07",
    },
    "inventory_turnover": {
        "group": "营运能力", "label": "存货周转率", "unit": "次/年", "is_pct": False,
        "warn_dir": "lt", "warn_threshold": 2.0, "good_threshold": 2.0,
        "rule_id": "F-08",
    },
    "asset_turnover": {
        "group": "营运能力", "label": "总资产周转率", "unit": "次/年", "is_pct": False,
        "warn_dir": None, "warn_threshold": None, "good_threshold": None,
        "rule_id": None,
    },
    # ── 盈利能力 ──
    "gross_margin": {
        "group": "盈利能力", "label": "毛利率", "unit": "%", "is_pct": True,
        "warn_dir": "lt", "warn_threshold": 0.1, "good_threshold": 0.2,
        "rule_id": "F-10",
    },
    "net_margin": {
        "group": "盈利能力", "label": "净利率", "unit": "%", "is_pct": True,
        "warn_dir": "lt", "warn_threshold": 0.0, "good_threshold": 0.05,
        "rule_id": None,
    },
    "roe": {
        "group": "盈利能力", "label": "净资产收益率", "unit": "%", "is_pct": True,
        "warn_dir": "lt", "warn_threshold": 0.0, "good_threshold": 0.0,
        "rule_id": "F-09",
    },
    "roa": {
        "group": "盈利能力", "label": "总资产收益率", "unit": "%", "is_pct": True,
        "warn_dir": None, "warn_threshold": None, "good_threshold": None,
        "rule_id": None,
    },
    # ── 成长能力 ──
    "revenue_yoy": {
        "group": "成长能力", "label": "营收同比", "unit": "%", "is_pct": True,
        "warn_dir": "lt", "warn_threshold": -0.2, "good_threshold": 0.0,
        "rule_id": "F-04",
    },
    "profit_yoy": {
        "group": "成长能力", "label": "净利润同比", "unit": "%", "is_pct": True,
        "warn_dir": None, "warn_threshold": None, "good_threshold": 0.0,
        "rule_id": None,
    },
}


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def assess_financial_ratio(field: str, value: Any) -> str:
    """客观评级：预警 / 达标 / 无数据（0=弃权）。"""
    cfg = FINANCIAL_RATIOS.get(field)
    if not cfg:
        return "无数据"
    v = _to_float(value)
    if v == 0.0:
        return "无数据"
    warn_dir = cfg.get("warn_dir")
    threshold = cfg.get("warn_threshold")
    if warn_dir is None or threshold is None:
        return "达标"
    if warn_dir == "gt" and v > threshold:
        return "预警"
    if warn_dir == "lt" and v < threshold:
        return "预警"
    return "达标"


def format_financial_ratio(field: str, value: Any) -> str:
    """展示值：is_pct 比率 ×100，倍数保留 2 位；0=「无数据」。"""
    cfg = FINANCIAL_RATIOS.get(field)
    v = _to_float(value)
    if v == 0.0:
        return "无数据"
    if cfg and cfg.get("is_pct"):
        return f"{v * 100:.1f}%"
    return f"{v:.2f}"


def _fmt_factor(is_pct: bool, value: float | None) -> str | None:
    if value is None:
        return None
    if is_pct:
        return f"{value * 100:.1f}%"
    return f"{value:.2f}"


def dupont_breakdown(
    *,
    net_margin: Any,
    asset_turnover: Any,
    total_assets: Any,
    owner_equity: Any,
    roe: Any,
) -> dict[str, Any]:
    """杜邦分解：ROE = 净利率 × 总资产周转率 × 权益乘数。

    任一因子 0=弃权 或权益分母非正 → 该因子 value=None（弃权），不硬凑乘积。
    三因子方向：净利率=盈利质量、总资产周转率=营运效率、权益乘数=财务杠杆。
    """
    nm = _to_float(net_margin)
    at = _to_float(asset_turnover)
    ta = _to_float(total_assets)
    oe = _to_float(owner_equity)
    roe_v = _to_float(roe)

    equity_multiplier = (ta / oe) if oe > 0 else None
    factors = [
        {
            "field": "net_margin", "label": "净利率", "dir": "盈利质量",
            "is_pct": True, "value": nm if nm != 0.0 else None,
        },
        {
            "field": "asset_turnover", "label": "总资产周转率", "dir": "营运效率",
            "is_pct": False, "value": at if at != 0.0 else None,
        },
        {
            "field": "equity_multiplier", "label": "权益乘数", "dir": "财务杠杆",
            "is_pct": False, "value": equity_multiplier,
        },
    ]
    for f in factors:
        f["disp"] = _fmt_factor(f["is_pct"], f["value"])
    complete = all(f["value"] is not None for f in factors) and roe_v != 0.0
    return {
        "complete": complete,
        "factors": factors,
        "roe": roe_v if roe_v != 0.0 else None,
        "roe_disp": _fmt_factor(True, roe_v) if roe_v != 0.0 else None,
        "formula": "ROE = 净利率 × 总资产周转率 × 权益乘数",
    }
