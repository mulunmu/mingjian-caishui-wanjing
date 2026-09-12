"""对话/报告共用的 charts payload 构造。"""
from __future__ import annotations

from typing import Any

from app.services.assessment_weights import DIMENSION_LABELS, DIMENSION_WEIGHTS
from app.services.metric_registry import REVENUE_DEVIATION_WARN, revenue_deviation_warn_label
from app.services.report_templates import zh_industry

SIGNAL_X_LABELS = ["税务违法", revenue_deviation_warn_label(), "信用C/D/M"]
SIGNAL_BUCKET_KEYS = ("tax", "dev", "credit")


def attribution_radar_chart(
    attribution: dict[str, Any],
    *,
    name: str = "全样本",
    dims: list[str] | None = None,
) -> dict[str, Any] | None:
    """样本六维均分雷达图（来自 get_slice_attribution）。

    dims 非空时只展示这些维度（铁律：雷达 ⊆ 正文解析维度），用于按章节裁剪。
    """
    all_dims = attribution.get("dimensions") or {}
    if not all_dims:
        return None
    indicators: list[dict[str, Any]] = []
    values: list[float] = []
    caveats: list[dict[str, str]] = []
    for key in DIMENSION_WEIGHTS:
        if dims is not None and key not in dims:
            continue
        d = all_dims.get(key)
        if not d:
            continue
        label = d.get("label") or DIMENSION_LABELS.get(key, key)
        score = float(d.get("score") or 0)
        if key == "legal" and d.get("coverage") == "tax_illegal_only":
            label = f"{label}(低覆盖)"
            caveats.append(
                {
                    "dimension": "legal",
                    "message": "法律维仅覆盖税务违法，不含失信/诉讼；高分不代表完整合规",
                }
            )
        indicators.append({"name": label, "max": 100})
        values.append(score)
    if not indicators:
        return None
    scope = zh_industry(attribution.get("industry_l1"))
    label = f"{scope}行业" if scope else name
    payload: dict[str, Any] = {"indicators": indicators, "values": values, "name": label}
    if caveats:
        payload["caveats"] = caveats
    return {
        "type": "radar",
        "data": payload,
    }


def enterprise_radar_chart(
    ent: dict[str, Any],
    *,
    dims: list[str] | None = None,
) -> dict[str, Any] | None:
    """单企业多维雷达。

    dims 非空时只展示这些维度（铁律：雷达 ⊆ 正文已解析维度）；全空则弃权。
    """
    scores = ent.get("dimensions", {}) or {}
    indicators: list[dict[str, Any]] = []
    values: list[float] = []
    for key in DIMENSION_WEIGHTS:
        if dims is not None and key not in dims:
            continue
        score = float(scores.get(key, 0) or 0)
        if score <= 0:
            continue  # 0=弃权，不画入雷达
        indicators.append({"name": DIMENSION_LABELS.get(key, key), "max": 100})
        values.append(score)
    if not indicators:
        return None
    return {
        "type": "radar",
        "data": {
            "indicators": indicators,
            "values": values,
            "name": ent.get("enterprise_name", "") or ent.get("display_label", ""),
        },
    }


def signal_industry_heatmap(rows: list[Any]) -> dict[str, Any] | None:
    """行业 × 风险信号互斥分桶热力图；行业不足 2 时返回 None。"""
    from collections import defaultdict

    buckets: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"tax": set(), "dev": set(), "credit": set()}
    )

    def _f(v: Any) -> float:
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    for m in rows:
        eid = m.enterprise_id
        ind = m.industry_l1 or "其他"
        if int(getattr(m, "tax_violation_cnt", 0) or 0) > 0:
            buckets[ind]["tax"].add(eid)
        elif _f(m.revenue_deviation) >= REVENUE_DEVIATION_WARN:
            buckets[ind]["dev"].add(eid)
        elif (m.credit_level or "") in ("C", "D", "M"):
            buckets[ind]["credit"].add(eid)

    active = {
        ind: b
        for ind, b in buckets.items()
        if any(b[k] for k in SIGNAL_BUCKET_KEYS)
    }
    if len(active) < 2:
        return None

    y_labels = sorted(
        active.keys(),
        key=lambda k: -sum(len(active[k][kk]) for kk in SIGNAL_BUCKET_KEYS),
    )[:8]
    values: list[list[int]] = []
    for yi, ind in enumerate(y_labels):
        for xi, kk in enumerate(SIGNAL_BUCKET_KEYS):
            cnt = len(active[ind][kk])
            if cnt:
                values.append([xi, yi, cnt])
    if not values:
        return None

    return {
        "type": "heatmap",
        "data": {
            "x_labels": list(SIGNAL_X_LABELS),
            "y_labels": y_labels,
            "values": values,
        },
    }


def signal_pie_chart(bucket_tax: set[str], bucket_dev: set[str], bucket_credit: set[str]) -> dict[str, Any]:
    """风险信号互斥分桶饼图。"""
    return {
        "type": "pie",
        "data": {
            "labels": list(SIGNAL_X_LABELS),
            "series": [
                {
                    "name": "主体数（互斥）",
                    "values": [len(bucket_tax), len(bucket_dev), len(bucket_credit)],
                }
            ],
        },
    }


def signal_funnel_chart(
    total: int,
    bucket_tax: set[str],
    bucket_dev: set[str],
    bucket_credit: set[str],
) -> dict[str, Any]:
    """风险筛查漏斗：全样本 → 命中信号 → 税务/偏差 → 税务违法（逐级收窄）。"""
    unique = bucket_tax | bucket_dev | bucket_credit
    severe = len(bucket_tax) + len(bucket_dev)
    stages = [
        ("全样本", total),
        ("命中风险信号", len(unique)),
        ("税务违法或营收偏差", severe),
        ("税务违法", len(bucket_tax)),
    ]
    return {
        "type": "funnel",
        "data": {
            "labels": [s[0] for s in stages],
            "values": [s[1] for s in stages],
        },
    }


def correlation_scatter_chart(
    xs: list[float], ys: list[float], *, x_label: str, y_label: str
) -> dict[str, Any]:
    """两指标相关性散点图（x/y 已对齐）。"""
    return {
        "type": "scatter",
        "data": {
            "x": [float(x) for x in xs],
            "y": [float(y) for y in ys],
            "x_label": x_label,
            "y_label": y_label,
        },
    }
