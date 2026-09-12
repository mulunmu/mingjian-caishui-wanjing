"""
经营真实性引擎 — Benford 定律 + 多口径交叉偏差

参考 opensource/search_benford_law_compatibility（χ² / MAD）
三口径：增值税 ↔ 财报营业收入 ↔ 发票销项 ↔（可选）社保人数趋势
"""
from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Any, Iterable

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)

# Benford P(d) = log10(1 + 1/d)
BENFORD_PROBS = np.array([math.log10(1 + 1 / d) for d in range(1, 10)])

# Nigrini MAD 经验阈值（第一位数字）
MAD_THRESHOLDS = {
    "close": 0.006,
    "acceptable": 0.012,
    "marginally_acceptable": 0.015,
}


def leading_digit(n: float) -> int | None:
    try:
        x = abs(float(n))
    except (TypeError, ValueError):
        return None
    if x == 0 or math.isnan(x) or math.isinf(x):
        return None
    while x < 1:
        x *= 10
    while x >= 10:
        x /= 10
    d = int(x)
    return d if 1 <= d <= 9 else None


def extract_leading_digits(values: Iterable[float]) -> list[int]:
    digits = []
    for v in values:
        d = leading_digit(v)
        if d is not None:
            digits.append(d)
    return digits


def benford_test(values: Iterable[float], min_n: int = 50) -> dict[str, Any]:
    """
    χ² + MAD 检验是否符合 Benford 定律。
    conformity: close | acceptable | marginally_acceptable | nonconformity
    """
    digits = extract_leading_digits(values)
    n = len(digits)
    if n < min_n:
        return {
            "n": n,
            "conformity": "insufficient_sample",
            "violation": False,
            "chi2": None,
            "p_value": None,
            "mad": None,
            "label": f"样本量不足（{n} 家，需≥{min_n} 家）",
            "confidence": "inferred",
            "observed": {},
            "expected": {str(d): round(float(BENFORD_PROBS[d - 1]), 4) for d in range(1, 10)},
        }

    counts = Counter(digits)
    observed = np.array([counts.get(d, 0) for d in range(1, 10)], dtype=float)
    expected = BENFORD_PROBS * n
    chi2, p_value = stats.chisquare(observed, expected)
    proportions = observed / n
    mad = float(np.mean(np.abs(proportions - BENFORD_PROBS)))

    if mad < MAD_THRESHOLDS["close"]:
        conformity = "close"
    elif mad < MAD_THRESHOLDS["acceptable"]:
        conformity = "acceptable"
    elif mad < MAD_THRESHOLDS["marginally_acceptable"]:
        conformity = "marginally_acceptable"
    else:
        conformity = "nonconformity"

    # 违例：MAD 非符合 或 χ² 在 α=0.05 显著且 n 足够
    violation = conformity == "nonconformity" or (p_value < 0.05 and conformity != "close")

    return {
        "n": n,
        "conformity": conformity,
        "violation": bool(violation),
        "chi2": round(float(chi2), 4),
        "p_value": round(float(p_value), 6),
        "mad": round(mad, 6),
        "label": "本福特定律违例（数字分布异常）" if violation else "本福特定律符合（未见明显操纵）",
        "confidence": "computed",
        "observed": {str(d): int(counts.get(d, 0)) for d in range(1, 10)},
        "expected": {str(d): round(float(BENFORD_PROBS[d - 1] * n), 2) for d in range(1, 10)},
        "trace": {
            "method": "benford_chi2_mad",
            "reference": "search_benford_law_compatibility",
            "query_id": "Q_benford_first_digit",
        },
    }


def pairwise_deviation(a: float, b: float) -> float | None:
    if a is None or b is None:
        return None
    a, b = abs(float(a)), abs(float(b))
    base = max(a, b, 1.0)
    return abs(a - b) / base


def cross_source_deviation(
    *,
    vat_revenue: float | None = None,
    invoice_revenue: float | None = None,
    finance_revenue: float | None = None,
    cit_revenue: float | None = None,
    social_months: int | None = None,
) -> dict[str, Any]:
    """
    多口径交叉偏差率。
    返回平均偏差、最大偏差、可用源数量、疑似造假标记。
    """
    sources = {
        "vat": vat_revenue,
        "invoice": invoice_revenue,
        "finance": finance_revenue,
        "cit": cit_revenue,
    }
    present = {k: float(v) for k, v in sources.items() if v is not None and abs(float(v)) > 1}

    pairs = []
    keys = list(present.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            d = pairwise_deviation(present[keys[i]], present[keys[j]])
            if d is not None:
                pairs.append({"a": keys[i], "b": keys[j], "deviation": round(d, 4)})

    if not pairs:
        return {
            "source_count": len(present),
            "avg_deviation": None,
            "max_deviation": None,
            "pairs": [],
            "suspicious": False,
            "label": "可交叉口径不足",
            "confidence": "inferred",
            "social_months": social_months,
        }

    avg_d = sum(p["deviation"] for p in pairs) / len(pairs)
    max_d = max(p["deviation"] for p in pairs)
    from app.services.metric_registry import CROSS_AVG_DEVIATION_WARN, CROSS_MAX_DEVIATION_WARN

    # 平均偏差或最大偏差越线 → 疑似（阈值见 metric_registry，禁止写死）
    suspicious = avg_d >= CROSS_AVG_DEVIATION_WARN or max_d >= CROSS_MAX_DEVIATION_WARN

    return {
        "source_count": len(present),
        "sources": {k: round(v, 2) for k, v in present.items()},
        "avg_deviation": round(avg_d, 4),
        "max_deviation": round(max_d, 4),
        "pairs": pairs,
        "suspicious": suspicious,
        "label": "多口径偏差偏高（真实性存疑）" if suspicious else "多口径交叉基本一致",
        "confidence": "computed",
        "social_months": social_months,
        "trace": {
            "tables": ["syx_tax_value_added", "syx_invoice", "syx_tax_finance_profit_year"],
            "fields": ["vat_revenue", "invoice_revenue", "finance_revenue"],
            "query_id": "Q_cross_source_deviation",
        },
    }


def analyze_authenticity_from_metrics(m: Any) -> dict[str, Any]:
    """基于 CoreMetrics 行做交叉验证；Benford 需额外金额序列时单独调用。"""
    cross = cross_source_deviation(
        vat_revenue=float(getattr(m, "vat_revenue", 0) or 0),
        invoice_revenue=float(getattr(m, "invoice_revenue", 0) or 0),
        finance_revenue=float(getattr(m, "finance_revenue", 0) or 0),
        social_months=int(getattr(m, "social_months", 0) or 0),
    )
    # 已有 revenue_deviation 字段作辅助
    stored_dev = float(getattr(m, "revenue_deviation", 0) or 0)
    score = 100.0
    if cross.get("avg_deviation") is not None:
        score -= min(60.0, cross["avg_deviation"] * 100)
    score -= min(20.0, stored_dev * 40)
    if getattr(m, "social_trend", "") == "缩减":
        score -= 10

    return {
        "enterprise_id": getattr(m, "enterprise_id", None),
        "display_name": getattr(m, "display_name", None),
        "display_label": getattr(m, "display_label", None) or getattr(m, "enterprise_name", None),
        "industry_l1": getattr(m, "industry_l1", None),
        "authenticity_score": round(max(0.0, score), 2),
        "cross_source": cross,
        "stored_revenue_deviation": round(stored_dev, 4),
        "confidence": "computed",
    }


def load_finance_amounts_for_benford(limit_rows: int = 20000) -> list[float]:
    """从利润表/发票金额抽取数字做 Benford（行业整体）。"""
    from app.db.mysql import U, fetch_all

    amounts: list[float] = []
    try:
        rows = fetch_all(
            f"""
            SELECT current_year_accumulative_amount AS amt
            FROM syx_tax_finance_profit_year
            WHERE current_year_accumulative_amount IS NOT NULL
              AND ABS(current_year_accumulative_amount) >= 1
            LIMIT %s
            """,
            (limit_rows,),
        )
        amounts.extend(float(r["amt"]) for r in rows if r.get("amt") is not None)
    except Exception as e:
        logger.warning("benford profit load failed: %s", e)

    try:
        rows = fetch_all(
            """
            SELECT jshj AS amt FROM syx_invoice
            WHERE jshj IS NOT NULL AND ABS(jshj) >= 1
            LIMIT %s
            """,
            (limit_rows // 2,),
        )
        amounts.extend(float(r["amt"]) for r in rows if r.get("amt") is not None)
    except Exception as e:
        logger.warning("benford invoice load failed: %s", e)

    return amounts


def analyze_authenticity_batch(metrics: list[Any], industry_l1: str | None = None) -> dict[str, Any]:
    analyses = [analyze_authenticity_from_metrics(m) for m in metrics]
    suspicious = [a for a in analyses if a["cross_source"].get("suspicious")]
    avg_score = (
        sum(a["authenticity_score"] for a in analyses) / len(analyses) if analyses else 0
    )
    avg_dev = [
        a["cross_source"]["avg_deviation"]
        for a in analyses
        if a["cross_source"].get("avg_deviation") is not None
    ]

    # 切片金额 = 本切片（当前 metrics）主体金额，非全库快照。运行时只读 PG（CoreMetrics 营收列），
    # MySQL 源库离线也不影响 Benford。弃权优先于编造：<30 家时 benford_test 直接返回
    # conformity="insufficient_sample"、chi2=None，绝不回退全库 snapshot 硬凑数字。
    slice_amounts = [
        float(
            getattr(m, "finance_revenue", 0)
            or getattr(m, "vat_revenue", 0)
            or getattr(m, "invoice_revenue", 0)
            or 0
        )
        for m in metrics
    ]
    slice_amounts = [a for a in slice_amounts if abs(a) >= 1]

    # Benford 一律用本切片金额（行业切片与整体切片口径一致），不再读 engine_snapshots 全库快照。
    benford = benford_test(slice_amounts, min_n=30)
    benford_source = f"slice_metrics:{industry_l1}" if industry_l1 else "slice_metrics"

    scope_label = "本切片"

    return {
        "dimension": "industry" if industry_l1 else "overall",
        "industry_l1": industry_l1 or "整体",
        "sample_count": len(analyses),
        "avg_authenticity_score": round(avg_score, 2),
        "avg_cross_deviation": round(sum(avg_dev) / len(avg_dev), 4) if avg_dev else None,
        "suspicious_count": len(suspicious),
        "suspicious_rate": round(len(suspicious) / len(analyses), 4) if analyses else 0,
        "benford": benford,
        "benford_source": benford_source,
        "benford_scope": scope_label,
        "top_suspicious": sorted(
            [
                {
                    "enterprise_id": a.get("enterprise_id"),
                    "display_name": a.get("display_name"),
                    "display_label": a.get("display_label"),
                    "industry_l1": a.get("industry_l1"),
                    "authenticity_score": a["authenticity_score"],
                    "cross_avg_deviation": a["cross_source"].get("avg_deviation"),
                    "avg_deviation": a["cross_source"].get("avg_deviation"),
                    "cross_suspicious": True,
                    "label": a["cross_source"].get("label"),
                }
                for a in suspicious
            ],
            key=lambda x: x["authenticity_score"],
        )[:15],
        "confidence": "computed",
        "trace": {
            "table": "core_metrics",
            "fields": ["vat_revenue", "invoice_revenue", "finance_revenue", "revenue_deviation"],
            "query_id": "Q_authenticity_industry_slice",
        },
    }


def analyze_industry_authenticity(industry_l1: str | None = None) -> dict[str, Any]:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.db.urls import get_sync_engine
    from app.models.core_metrics import CoreMetrics

    with Session(get_sync_engine()) as session:
        q = select(CoreMetrics)
        if industry_l1:
            q = q.where(CoreMetrics.industry_l1 == industry_l1)
        metrics = list(session.scalars(q).all())
    return analyze_authenticity_batch(metrics, industry_l1=industry_l1)


def fake_benford_violation_sample() -> dict[str, Any]:
    """验收用：人为构造偏向数字 5/6/7/8/9 的序列，应触发 Benford 违例。"""
    # 大量以 8、9 开头 → 明显偏离 Benford
    manipulated = [8000 + i * 17 for i in range(80)] + [9000 + i * 13 for i in range(80)]
    return benford_test(manipulated, min_n=50)


def natural_benford_sample() -> dict[str, Any]:
    """验收对照：近似 Benford 的对数均匀分布。"""
    rng = np.random.default_rng(42)
    # log-uniform → 近似 Benford
    vals = 10 ** rng.uniform(2, 6, size=500)
    return benford_test(vals.tolist(), min_n=50)
