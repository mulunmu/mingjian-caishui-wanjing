from decimal import Decimal
import time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics, LegalEvent
from app.services.assessment_weights import DIMENSION_LABELS, DIMENSION_WEIGHTS, effective_dimension_weights
from app.services.metric_registry import REVENUE_DEVIATION_WARN
from app.services.report_templates import zh_industry

EVENT_DEDUCTIONS: dict[str, float] = {
    "dishonesty": 30,
    "execution": 20,
    "tax_violation": 15,
    "tax_audit": 12,
    "tax_arrears": 10,
    "civil_lawsuit": 5,
    "admin_penalty": 10,
}
EVENT_LABELS: dict[str, str] = {
    "tax_violation": "税务违法",
    "tax_audit": "税务稽查",
    "tax_arrears": "欠税",
    "dishonesty": "失信",
    "execution": "被执行",
    "civil_lawsuit": "民事诉讼",
    "admin_penalty": "行政处罚",
}

_CACHE: dict = {"metrics": [], "legal_by_ent": {}, "loaded_at": None}
CACHE_TTL_SECONDS = int(__import__("os").getenv("ASSESSMENT_CACHE_TTL", "300"))

SOCIAL_TREND_SCORE = {"增长": 100, "稳定": 70, "缩减": 30}
Z_SCORE_LEVEL = {"安全": 80, "灰色": 50, "困境": 20}
RISK_LEVELS = [
    (80, "低风险"),
    (65, "中低风险"),
    (50, "中等风险"),
    (35, "中高风险"),
    (0, "高风险"),
]
NO_BENCHMARK_INDUSTRIES = {"非上市", "其他"}


async def _ensure_cache(db: AsyncSession) -> list[CoreMetrics]:
    loaded = _CACHE.get("loaded_at")
    stale = loaded is None or (time.time() - loaded) > CACHE_TTL_SECONDS
    if not _CACHE["metrics"] or stale:
        if stale and _CACHE["metrics"]:
            _CACHE["metrics"] = []
            _CACHE["legal_by_ent"] = {}
        result = await db.execute(select(CoreMetrics))
        _CACHE["metrics"] = list(result.scalars().all())
        ev_result = await db.execute(select(LegalEvent))
        events = list(ev_result.scalars().all())
        by_ent: dict[str, list[LegalEvent]] = {}
        for ev in events:
            by_ent.setdefault(ev.enterprise_id, []).append(ev)
        _CACHE["legal_by_ent"] = by_ent
        _CACHE["loaded_at"] = time.time()
    return _CACHE["metrics"]


async def refresh_cache(db: AsyncSession) -> None:
    _CACHE["metrics"] = []
    _CACHE["legal_by_ent"] = {}
    await _ensure_cache(db)


def _percentile(value: float, population: list[float]) -> float:
    if not population:
        return 50.0
    if len(population) == 1:
        return 50.0
    rank = sum(1 for v in population if v <= value)
    return (rank - 1) / (len(population) - 1) * 100


def _to_float(v: Decimal | int | float | None) -> float:
    if v is None:
        return 0.0
    return float(v)


def _present(v: Decimal | int | float | None) -> bool:
    """比率字段 0=弃权哨兵，不得混入分位总体或扣分阈值。"""
    return _to_float(v) != 0.0


def _peer_vals(peers: list[CoreMetrics], attr: str) -> list[float]:
    return [_to_float(getattr(x, attr)) for x in peers if _present(getattr(x, attr, None))]


def _pct_or_neutral(value: float, population: list[float], *, present: bool) -> float:
    if not present or not population:
        return 50.0
    return _percentile(value, population)


def _debt_warn_threshold() -> float:
    from app.services.financial_benchmarks import FINANCIAL_RATIOS

    return float(FINANCIAL_RATIOS["debt_ratio"]["warn_threshold"])


def _risk_level(score: float) -> str:
    for threshold, label in RISK_LEVELS:
        if score >= threshold:
            return label
    return "高风险"


def _tax_violation_deductions(viol_cnt: int, high_sev_cnt: int) -> list[dict]:
    """税务违法 vs 高危：高危是违法子集，禁止 15N+20N 重复全额扣分。

    口径：基础扣分 tax_violation×15；对重叠的高危仅加严重度加成×5（合计≈20）；
    仅当 high_severity > tax_violation（独立高危、无违法计数）时按×20 单独扣。
    """
    viol = max(0, int(viol_cnt or 0))
    high = max(0, int(high_sev_cnt or 0))
    out: list[dict] = []
    if viol > 0:
        out.append({"item": "税务违法", "deduction": viol * 15, "count": viol})
        premium_n = min(high, viol)
        if premium_n:
            out.append({"item": "高危事件加成", "deduction": premium_n * 5, "count": premium_n})
        orphan = max(0, high - viol)
        if orphan:
            out.append({"item": "高危事件", "deduction": orphan * 20, "count": orphan})
    elif high > 0:
        out.append({"item": "高危事件", "deduction": high * 20, "count": high})
    return out


def _calc_tax_health(m: CoreMetrics) -> tuple[float, list[dict], list[dict]]:
    positive: list[dict] = []
    negative: list[dict] = []
    credit_contrib = _to_float(m.credit_score) * 0.4
    positive.append({"item": "纳税信用", "contribution": round(credit_contrib, 2)})
    # 0=弃权哨兵：与洞察 T-04 / _present 对齐，不把「无缴款记录」当成准时率 0 扣分
    on_time_present = _present(m.tax_on_time_rate)
    tax_rate_contrib = (_to_float(m.tax_on_time_rate) * 100 * 0.3) if on_time_present else 0.0
    if on_time_present:
        positive.append({"item": "纳税准时率", "contribution": round(tax_rate_contrib, 2)})
    else:
        positive.append({"item": "纳税准时率（数据弃权）", "contribution": 0.0})

    if m.tax_arrears_cnt:
        d = m.tax_arrears_cnt * 10
        negative.append({"item": "欠税记录", "deduction": d, "count": m.tax_arrears_cnt})
    negative.extend(
        _tax_violation_deductions(
            int(getattr(m, "tax_violation_cnt", 0) or 0),
            int(getattr(m, "high_severity_cnt", 0) or 0),
        )
    )
    if m.is_dishonesty:
        negative.append({"item": "失信标志", "deduction": 25, "count": 1})
    if m.is_execution:
        negative.append({"item": "被执行标志", "deduction": 25, "count": 1})

    # 税务画像补充信号（阈值与洞察规则 T-05~T-08 / T-10 对齐，0=弃权不误判）
    late_cnt = int(getattr(m, "tax_late_penalty_cnt", 0) or 0)
    if late_cnt > 0:
        negative.append({"item": "滞纳金/罚款", "deduction": min(20, late_cnt * 5), "count": late_cnt})
    corr = int(getattr(m, "correction_times", 0) or 0)
    if corr >= 80:
        negative.append({"item": "申报更正异常频繁", "deduction": 10, "count": corr})
    if 0 < _to_float(m.vat_burden) < 0.005:
        negative.append({"item": "增值税税负率明显偏低", "deduction": 15, "count": 1})
    if 0 < _to_float(m.income_tax_burden) < 0.001:
        negative.append({"item": "所得税税负率明显偏低", "deduction": 15, "count": 1})
    change = int(getattr(m, "change_cnt", 0) or 0)
    if change >= 15:
        negative.append({"item": "变更登记频繁", "deduction": 10, "count": change})

    deduct = sum(n["deduction"] for n in negative)
    result = credit_contrib + tax_rate_contrib - deduct
    # 信用/准时率量纲若异常，封顶 100，避免 overall 无上界
    return max(-50.0, min(100.0, result)), positive, negative


def _calc_invoice(m: CoreMetrics, all_metrics: list[CoreMetrics]) -> dict:
    """发票健康：进销分散度（集中度逆向分位）+ 作废/单价质量扣分。

    集中度 0=弃权（源缺失），从分散度分量剔除；三字段全弃权返回 50 中性分。
    作废/单价信号与洞察规则 I-10 / I-11 同阈值。
    """
    cust_vals = [_to_float(x.customer_concentration) for x in all_metrics if _to_float(x.customer_concentration) > 0]
    supp_vals = [_to_float(x.supplier_concentration) for x in all_metrics if _to_float(x.supplier_concentration) > 0]
    cate_vals = [_to_float(x.category_concentration) for x in all_metrics if _to_float(x.category_concentration) > 0]

    positive: list[dict] = []
    negative: list[dict] = []
    parts: list[tuple[str, float, float]] = []
    for label, w, val, pop in (
        ("客户分散度分位", 0.35, _to_float(m.customer_concentration), cust_vals),
        ("供应商分散度分位", 0.35, _to_float(m.supplier_concentration), supp_vals),
        ("品目分散度分位", 0.30, _to_float(m.category_concentration), cate_vals),
    ):
        if val > 0:
            parts.append((label, w, 100 - _percentile(val, pop)))

    note = ""
    if not parts:
        score = 50.0
        positive.append({"item": "无集中度样本", "contribution": 50})
        note = "集中度全弃权"
    else:
        total_w = sum(w for _, w, _ in parts)
        score = sum(w * p for _, w, p in parts) / total_w
        for label, w, p in parts:
            positive.append({"item": label, "contribution": round(w * p / total_w, 2)})

    # 发票质量绝对扣分（作废占比 / 单价离散）
    void_cnt = int(getattr(m, "void_invoice_cnt", 0) or 0)
    inv_cnt = int(getattr(m, "invoice_cnt", 0) or 0)
    void_ratio = void_cnt / inv_cnt if inv_cnt > 0 else 0.0
    if void_ratio > 0.15:
        negative.append({"item": "作废发票占比异常", "deduction": 15, "count": void_cnt})
    if _to_float(m.unit_price_ratio) > 100000:
        negative.append({"item": "单价离散异常", "deduction": 10, "count": 1})

    for n in negative:
        score -= n["deduction"]
    score = max(0.0, min(100.0, score))

    return {
        "score": score,
        "positive": positive,
        "negative": negative,
        "engine": "invoice_concentration",
        "note": note,
    }


def _calc_authenticity(m: CoreMetrics, all_metrics: list[CoreMetrics]) -> dict:
    from app.services.authenticity_engine import analyze_authenticity_from_metrics

    eng = analyze_authenticity_from_metrics(m)
    score = float(eng.get("authenticity_score") or 0)
    cross = eng.get("cross_source") or {}
    stored_dev = float(eng.get("stored_revenue_deviation") or 0)

    positive = [{"item": "交叉验证得分", "contribution": round(score, 2)}]
    if cross.get("label"):
        positive.append({"item": cross["label"], "contribution": round(max(0, 100 - (cross.get("avg_deviation") or 0) * 100), 2)})

    negative: list[dict] = []
    if cross.get("suspicious"):
        negative.append({"item": "多源营收偏差可疑", "deduction": round(min(40, (cross.get("avg_deviation") or 0) * 100), 2)})
    if stored_dev >= REVENUE_DEVIATION_WARN:
        negative.append({"item": "营收偏差过大", "deduction": round((stored_dev - REVENUE_DEVIATION_WARN) * 100, 2)})
    if m.social_trend == "缩减":
        negative.append({"item": "社保趋势缩减", "deduction": 10})

    return {
        "score": score,
        "positive": positive,
        "negative": negative,
        "revenue_deviation_component": stored_dev,
        "cross_avg_deviation": cross.get("avg_deviation"),
        "engine": "authenticity_engine",
    }


def _calc_industry(m: CoreMetrics, all_metrics: list[CoreMetrics]) -> dict:
    if m.industry_l1 in NO_BENCHMARK_INDUSTRIES:
        return {
            "score": 50.0,
            "positive": [{"item": "无行业对标样本", "contribution": 50}],
            "negative": [],
            "peer_rank": None,
            "peer_total": 0,
            "note": "非上市/无对标",
        }
    if m.industry_l2 == "新注册":
        return {
            "score": 40.0,
            "positive": [],
            "negative": [{"item": "经营数据不足12个月", "deduction": 10}],
            "peer_rank": None,
            "peer_total": 0,
            "note": "新注册企业",
        }

    peers = [
        x for x in all_metrics
        if x.industry_l1 == m.industry_l1 and x.industry_l1 not in NO_BENCHMARK_INDUSTRIES
    ]
    if len(peers) <= 1:
        return {
            "score": 50.0,
            "positive": [{"item": "同行业样本不足", "contribution": 50}],
            "negative": [],
            "peer_rank": 1,
            "peer_total": 1,
        }

    peer_margins = [_to_float(x.profit_margin) for x in peers]
    peer_yoys = [_to_float(x.revenue_yoy) for x in peers]
    margin_pct = _percentile(_to_float(m.profit_margin), peer_margins)
    yoy_pct = _percentile(_to_float(m.revenue_yoy), peer_yoys)
    score = margin_pct * 0.5 + yoy_pct * 0.5

    ranking = sorted(
        peers,
        key=lambda x: _to_float(x.profit_margin) + _to_float(x.revenue_yoy),
        reverse=True,
    )
    peer_rank = next(i + 1 for i, x in enumerate(ranking) if x.enterprise_id == m.enterprise_id)

    positive = [
        {"item": "利润率行业分位", "contribution": round(margin_pct * 0.5, 2)},
        {"item": "营收增速分位", "contribution": round(yoy_pct * 0.5, 2)},
    ]
    negative: list[dict] = []
    if peer_rank > len(peers) * 0.7:
        negative.append({"item": "同行业排名靠后", "deduction": 10})

    return {
        "score": score,
        "positive": positive,
        "negative": negative,
        "peer_rank": peer_rank,
        "peer_total": len(peers),
        "profit_margin_percentile": margin_pct,
        "revenue_yoy_percentile": yoy_pct,
    }


def _calc_finance(m: CoreMetrics, all_metrics: list[CoreMetrics]) -> dict:
    """财务健康：有完整三大报表 → 四能力比率分位；无 → 代理口径。"""
    fin_peers = [x for x in all_metrics if getattr(x, "has_financial_statements", False)]
    if getattr(m, "has_financial_statements", False) and len(fin_peers) >= 5:
        return _calc_finance_ratios(m, fin_peers)
    return _calc_finance_proxy(m, all_metrics)


def _calc_finance_ratios(m: CoreMetrics, peers: list[CoreMetrics]) -> dict:
    """四能力比率分位：偿债 30% / 盈利 30% / 营运 20% / 成长 20%。

    每项比率在同业（有报表样本）内取分位，越高越好（资产负债率取逆向分位）。
    弃权项（比率=0）排除出分位总体；主体弃权时该分量取中性 50。
    """
    curr = _peer_vals(peers, "current_ratio")
    quick = _peer_vals(peers, "quick_ratio")
    debts = _peer_vals(peers, "debt_ratio")
    gross = _peer_vals(peers, "gross_margin")
    netm = _peer_vals(peers, "net_margin")
    roes = _peer_vals(peers, "roe")
    recv = _peer_vals(peers, "receivables_turnover")
    inv = _peer_vals(peers, "inventory_turnover")
    asset = _peer_vals(peers, "asset_turnover")
    yoys = _peer_vals(peers, "revenue_yoy")
    pyoys = _peer_vals(peers, "profit_yoy")

    mv = {
        "current_ratio": _to_float(m.current_ratio),
        "quick_ratio": _to_float(m.quick_ratio),
        "debt_ratio": _to_float(m.debt_ratio),
        "gross_margin": _to_float(m.gross_margin),
        "net_margin": _to_float(m.net_margin),
        "roe": _to_float(m.roe),
        "receivables_turnover": _to_float(m.receivables_turnover),
        "inventory_turnover": _to_float(m.inventory_turnover),
        "asset_turnover": _to_float(m.asset_turnover),
        "revenue_yoy": _to_float(m.revenue_yoy),
        "profit_yoy": _to_float(m.profit_yoy),
    }

    curr_pct = _pct_or_neutral(mv["current_ratio"], curr, present=_present(m.current_ratio))
    quick_pct = _pct_or_neutral(mv["quick_ratio"], quick, present=_present(m.quick_ratio))
    debt_base = _pct_or_neutral(mv["debt_ratio"], debts, present=_present(m.debt_ratio))
    debt_rev = 100 - debt_base if _present(m.debt_ratio) else 50.0
    gross_pct = _pct_or_neutral(mv["gross_margin"], gross, present=_present(m.gross_margin))
    netm_pct = _pct_or_neutral(mv["net_margin"], netm, present=_present(m.net_margin))
    roe_pct = _pct_or_neutral(mv["roe"], roes, present=_present(m.roe))
    recv_pct = _pct_or_neutral(mv["receivables_turnover"], recv, present=_present(m.receivables_turnover))
    inv_pct = _pct_or_neutral(mv["inventory_turnover"], inv, present=_present(m.inventory_turnover))
    asset_pct = _pct_or_neutral(mv["asset_turnover"], asset, present=_present(m.asset_turnover))
    yoy_pct = _pct_or_neutral(mv["revenue_yoy"], yoys, present=_present(m.revenue_yoy))
    pyoy_pct = _pct_or_neutral(mv["profit_yoy"], pyoys, present=_present(m.profit_yoy))

    solvency = curr_pct * 0.4 + quick_pct * 0.3 + debt_rev * 0.3
    profitability = gross_pct * 0.35 + netm_pct * 0.35 + roe_pct * 0.3
    operation = recv_pct * 0.4 + inv_pct * 0.3 + asset_pct * 0.3
    growth = yoy_pct * 0.5 + pyoy_pct * 0.5

    score = solvency * 0.3 + profitability * 0.3 + operation * 0.2 + growth * 0.2

    positive = [
        {"item": "偿债能力分", "contribution": round(solvency * 0.3, 2)},
        {"item": "盈利能力分", "contribution": round(profitability * 0.3, 2)},
        {"item": "营运能力分", "contribution": round(operation * 0.2, 2)},
        {"item": "成长能力分", "contribution": round(growth * 0.2, 2)},
    ]
    negative: list[dict] = []
    if 0 < _to_float(m.current_ratio) < 1.0:
        negative.append({"item": "流动比率<1", "deduction": 10})
    debt_thr = _debt_warn_threshold()
    if _present(m.debt_ratio) and _to_float(m.debt_ratio) > debt_thr:
        negative.append({"item": "资产负债率过高", "deduction": 10})
    if _present(m.roe) and _to_float(m.roe) < 0:
        negative.append({"item": "净资产收益率为负", "deduction": 10})

    return {
        "score": score,
        "positive": positive,
        "negative": negative,
        "engine": "four_capabilities",
        "solvency_score": round(solvency, 2),
        "profitability_score": round(profitability, 2),
        "operation_score": round(operation, 2),
        "growth_score": round(growth, 2),
        "current_ratio_percentile": round(curr_pct, 1),
        "gross_margin_percentile": round(gross_pct, 1),
        "net_margin_percentile": round(netm_pct, 1),
        "roe_percentile": round(roe_pct, 1),
        "receivables_turnover_percentile": round(recv_pct, 1),
    }


def _calc_finance_proxy(m: CoreMetrics, all_metrics: list[CoreMetrics]) -> dict:
    """代理口径（无三大报表样本）：利润率 / 营收增速 / 负债率 / 现金流健康度。"""
    margins = _peer_vals(all_metrics, "profit_margin")
    yoys = _peer_vals(all_metrics, "revenue_yoy")
    debts = _peer_vals(all_metrics, "debt_ratio")
    margin_pct = _pct_or_neutral(_to_float(m.profit_margin), margins, present=_present(m.profit_margin))
    yoy_pct = _pct_or_neutral(_to_float(m.revenue_yoy), yoys, present=_present(m.revenue_yoy))
    debt_base = _pct_or_neutral(_to_float(m.debt_ratio), debts, present=_present(m.debt_ratio))
    debt_rev_pct = 100 - debt_base if _present(m.debt_ratio) else 50.0
    cf_level = getattr(m, "cash_flow_level", None) or m.z_score_level
    cf_score = {"健康": 80, "一般": 50, "承压": 20, "安全": 80, "灰色": 50, "困境": 20}.get(cf_level, 50)
    score = margin_pct * 0.3 + yoy_pct * 0.25 + debt_rev_pct * 0.2 + cf_score * 0.25

    positive = [
        {"item": "利润率分位", "contribution": round(margin_pct * 0.3, 2)},
        {"item": "营收增速分位", "contribution": round(yoy_pct * 0.25, 2)},
        {"item": "负债率逆向分位", "contribution": round(debt_rev_pct * 0.2, 2)},
        {"item": "现金流健康", "contribution": round(cf_score * 0.25, 2)},
    ]
    negative: list[dict] = []
    debt_thr = _debt_warn_threshold()
    if _present(m.debt_ratio) and _to_float(m.debt_ratio) > debt_thr:
        negative.append({"item": "资产负债率过高", "deduction": 15})
    if cf_level in ("承压", "困境"):
        negative.append({"item": "经营现金流承压", "deduction": 20})

    return {
        "score": score,
        "positive": positive,
        "negative": negative,
        "engine": "proxy",
        "profit_margin_percentile": margin_pct,
        "revenue_yoy_percentile": yoy_pct,
        "debt_ratio_reverse_percentile": debt_rev_pct,
        "cash_flow_level_score": cf_score,
    }


def _warning_signals(m: CoreMetrics, all_metrics: list[CoreMetrics], legal_score: float) -> list[str]:
    signals: list[str] = []
    if _present(m.tax_on_time_rate) and _to_float(m.tax_on_time_rate) < 0.8:
        signals.append("tax_on_time_rate_low")
    medians = sorted(_to_float(x.invoice_monthly_avg) for x in all_metrics if _to_float(x.invoice_monthly_avg) > 0)
    median_inv = medians[len(medians) // 2] if medians else 0
    if median_inv > 0 and _to_float(m.invoice_monthly_avg) < median_inv * 0.5:
        signals.append("invoice_monthly_avg_drop")
    if m.credit_level in ("C", "D", "M"):
        signals.append("credit_level_risk")
    if m.social_trend == "缩减":
        signals.append("social_trend_shrink")
    # 与洞察 A-01 统一阈值（见 metric_registry.REVENUE_DEVIATION_WARN）
    if _present(m.revenue_deviation) and _to_float(m.revenue_deviation) >= REVENUE_DEVIATION_WARN:
        signals.append("revenue_deviation_high")
    if legal_score < 50:
        signals.append("legal_compliance_risk")
    if m.is_dishonesty or m.is_execution:
        signals.append("legal_enforcement_risk")
    return signals


def _attribution_summary(
    m: CoreMetrics,
    dim_scores: dict[str, float],
    dim_attr: dict[str, dict],
    overall: float,
) -> str:
    """模板归因总结（后续可接 LLM）"""
    drag: list[str] = []
    for key, label in DIMENSION_LABELS.items():
        score = dim_scores.get(key, 50)
        if score < 45:
            negs = dim_attr.get(key, {}).get("negative", [])
            if negs:
                drag.append(f"{label}（{negs[0]['item']}）")
            else:
                drag.append(f"{label}偏低")
    label = getattr(m, "display_name", None) or getattr(m, "display_label", None) or "样本"
    risk = _risk_level(overall)
    if drag:
        return (
            f"{label}综合风险等级「{risk}」，"
            f"主要拖累因素：{'、'.join(drag[:3])}。"
            f"建议优先排查相关指标。"
        )
    strengths = [label for key, label in DIMENSION_LABELS.items() if dim_scores.get(key, 0) >= 70]
    if strengths:
        return (
            f"{label}综合风险等级「{risk}」，"
            f"{'、'.join(strengths[:2])}表现较好，整体风险可控。"
        )
    return (
        f"{label}综合风险等级「{risk}」，"
        f"各维度表现中等，建议关注核心指标变化。"
    )


def _build_dimension_details(
    tax: float, auth: dict, inv: dict, industry: dict, legal: dict, fin: dict, weights: dict[str, float] | None = None
) -> dict:
    w = weights or DIMENSION_WEIGHTS
    def _extra(d: dict) -> dict:
        return {k: round(v, 2) if isinstance(v, float) else v for k, v in d.items() if k not in ("score", "positive", "negative")}

    legal_detail = {
        "score": round(legal["score"], 2),
        "weight": DIMENSION_WEIGHTS["legal"],
        "effective_weight": round(w.get("legal", DIMENSION_WEIGHTS["legal"]), 4),
        "label": DIMENSION_LABELS["legal"],
        "event_count": legal["event_count"],
        "coverage": legal.get("coverage"),
        "coverage_note": legal.get("coverage_note"),
    }
    return {
        "tax_health": {"score": round(tax, 2), "weight": w["tax_health"], "label": DIMENSION_LABELS["tax_health"]},
        "authenticity": {"score": round(auth["score"], 2), "weight": w["authenticity"], "label": DIMENSION_LABELS["authenticity"], **_extra(auth)},
        "invoice": {"score": round(inv["score"], 2), "weight": w["invoice"], "label": DIMENSION_LABELS["invoice"], **_extra(inv)},
        "industry": {"score": round(industry["score"], 2), "weight": w["industry"], "label": DIMENSION_LABELS["industry"], **_extra(industry)},
        "legal": legal_detail,
        "finance": {"score": round(fin["score"], 2), "weight": w["finance"], "label": DIMENSION_LABELS["finance"], **_extra(fin)},
    }


def _calc_legal_score(m: CoreMetrics, events: list[LegalEvent] | None = None) -> dict:
    """法律合规分。

    源库仅有 syx_tax_illega（税务违法）与欠税等税务侧信号；
    无失信/被执行/诉讼表时，不以 is_dishonesty=False 假装覆盖全司法面。
    """
    events = events or []
    score = 100.0
    negative: list[dict] = []
    positive: list[dict] = []
    type_counts: dict[str, int] = {}
    for ev in events:
        type_counts[ev.event_type] = type_counts.get(ev.event_type, 0) + 1
    for et, cnt in type_counts.items():
        deduct = EVENT_DEDUCTIONS.get(et, 5) * cnt
        score -= deduct
        negative.append({"item": EVENT_LABELS.get(et, et), "deduction": round(deduct, 2), "count": cnt})
    # 仅当标志为 True（未来接入外部司法源）时才扣分；False 不表示「已核实无失信」
    if m.is_dishonesty and type_counts.get("dishonesty", 0) == 0:
        score -= 30
        negative.append({"item": "失信记录(标志)", "deduction": 30, "count": 1})
    if m.is_execution and type_counts.get("execution", 0) == 0:
        score -= 20
        negative.append({"item": "被执行(标志)", "deduction": 20, "count": 1})

    # 税务侧字段（core_metrics）— 无司法事件表时仍反映违法/欠税信号
    # 事件表已计入 tax_violation 时，不再用 metrics 计数重复扣（含 high_severity 同源池）
    viol_cnt = int(getattr(m, "tax_violation_cnt", 0) or 0)
    arrears_cnt = int(getattr(m, "tax_arrears_cnt", 0) or 0)
    high_sev = int(getattr(m, "high_severity_cnt", 0) or 0)
    events_have_violation = type_counts.get("tax_violation", 0) > 0
    if viol_cnt > 0 and not events_have_violation:
        deduct = min(45.0, viol_cnt * 12.0)
        score -= deduct
        negative.append({"item": "税务违法记录", "deduction": round(deduct, 2), "count": viol_cnt})
    if arrears_cnt > 0:
        deduct = min(30.0, arrears_cnt * 10.0)
        score -= deduct
        negative.append({"item": "欠税记录", "deduction": round(deduct, 2), "count": arrears_cnt})
    if high_sev > 0 and not events_have_violation:
        # 与 _tax_violation_deductions 同口径：重叠部分仅严重度加成，禁止与 viol 全额双扣
        if viol_cnt > 0:
            premium_n = min(high_sev, viol_cnt)
            orphan = max(0, high_sev - viol_cnt)
            if premium_n:
                deduct = min(25.0, premium_n * 5.0)
                score -= deduct
                negative.append(
                    {"item": "高严重度税务事件加成", "deduction": round(deduct, 2), "count": premium_n}
                )
            if orphan:
                deduct = min(25.0, orphan * 8.0)
                score -= deduct
                negative.append(
                    {"item": "高严重度税务事件", "deduction": round(deduct, 2), "count": orphan}
                )
        else:
            deduct = min(25.0, high_sev * 8.0)
            score -= deduct
            negative.append({"item": "高严重度税务事件", "deduction": round(deduct, 2), "count": high_sev})

    score = max(0.0, min(100.0, score))
    coverage_note = "覆盖税务违法/欠税/稽查等税务侧事件；源库无失信/被执行/诉讼表"
    if not negative:
        positive.append({"item": "税务侧无重大违法事件", "contribution": round(score, 2)})
    elif score >= 60:
        positive.append({"item": "税务违法风险整体可控", "contribution": round(score * 0.3, 2)})
    return {
        "score": round(score, 2),
        "event_count": len(events),
        "positive": positive,
        "negative": negative,
        "coverage": "tax_illegal_only",
        "coverage_note": coverage_note,
    }


def _build_result(
    m: CoreMetrics,
    all_metrics: list[CoreMetrics],
    legal_events: list[LegalEvent] | None = None,
) -> dict:
    tax, tax_pos, tax_neg = _calc_tax_health(m)
    auth = _calc_authenticity(m, all_metrics)
    inv = _calc_invoice(m, all_metrics)
    industry = _calc_industry(m, all_metrics)
    legal = _calc_legal_score(m, legal_events or [])
    fin = _calc_finance(m, all_metrics)

    weights = effective_dimension_weights(legal.get("coverage"))

    dim_scores = {
        "tax_health": tax,
        "authenticity": auth["score"],
        "invoice": inv["score"],
        "industry": industry["score"],
        "legal": legal["score"],
        "finance": fin["score"],
    }

    overall = sum(dim_scores[k] * weights[k] for k in weights)
    overall = max(0.0, min(100.0, overall))

    dim_attr = {
        "tax_health": {"positive": tax_pos, "negative": tax_neg},
        "authenticity": {"positive": auth["positive"], "negative": auth["negative"]},
        "invoice": {"positive": inv["positive"], "negative": inv["negative"]},
        "industry": {"positive": industry["positive"], "negative": industry["negative"]},
        "legal": {"positive": legal["positive"], "negative": legal["negative"]},
        "finance": {"positive": fin["positive"], "negative": fin["negative"]},
    }

    attribution = {
        "dimensions": {
            key: {
                "score": round(dim_scores[key], 2),
                "weight": weights[key],
                "label": DIMENSION_LABELS[key],
                "positive": dim_attr[key]["positive"],
                "negative": dim_attr[key]["negative"],
                "net_contribution": round(dim_scores[key] * weights[key], 2),
            }
            for key in weights
        },
        "summary": _attribution_summary(m, dim_scores, dim_attr, overall),
    }

    display_label = getattr(m, "display_label", None) or "样本"
    display_name = getattr(m, "display_name", None)
    return {
        "enterprise_id": m.enterprise_id,
        "enterprise_name": display_name or display_label,  # 优先可读名「企业N」，回退匿名标签
        "display_name": display_name,
        "display_label": display_label,
        "credit_level": m.credit_level,
        "tax_on_time_rate": (
            round(_to_float(m.tax_on_time_rate), 4) if _present(m.tax_on_time_rate) else None
        ),
        "invoice_monthly_avg": m.invoice_monthly_avg,
        "revenue_deviation": round(_to_float(m.revenue_deviation), 4),
        "social_trend": m.social_trend,
        "industry_l1": m.industry_l1,
        "industry_l2": m.industry_l2,
        "province": m.province,
        "city": m.city,
        "overall_score": round(overall, 2),
        "risk_level": _risk_level(overall),
        "dimensions": {k: round(v, 2) for k, v in dim_scores.items()},
        "dimension_details": _build_dimension_details(tax, auth, inv, industry, legal, fin, weights),
        "attribution": attribution,
        "warning_signals": _warning_signals(m, all_metrics, legal["score"]),
    }


def _build_from_cache(m: CoreMetrics, all_metrics: list[CoreMetrics]) -> dict:
    events = _CACHE.get("legal_by_ent", {}).get(m.enterprise_id, [])
    return _build_result(m, all_metrics, events)


async def calculate(db: AsyncSession, enterprise_id: str) -> dict | None:
    all_metrics = await _ensure_cache(db)
    target = next((m for m in all_metrics if m.enterprise_id == enterprise_id), None)
    if not target:
        return None
    return _build_from_cache(target, all_metrics)


async def calculate_dimensions(db: AsyncSession, enterprise_id: str) -> dict | None:
    result = await calculate(db, enterprise_id)
    if not result:
        return None
    return {
        "enterprise_id": result["enterprise_id"],
        "dimensions": result["dimension_details"],
        "attribution": result["attribution"],
        "overall_score": result["overall_score"],
        "risk_level": result["risk_level"],
    }


async def calculate_pk(db: AsyncSession, enterprise_ids: list[str]) -> list[dict]:
    all_metrics = await _ensure_cache(db)
    by_id = {m.enterprise_id: m for m in all_metrics}
    return [_build_from_cache(by_id[eid], all_metrics) for eid in enterprise_ids if eid in by_id]


async def list_all(db: AsyncSession) -> list[dict]:
    """返回全部样本评估摘要（匿名标签）"""
    all_metrics = await _ensure_cache(db)
    return [_build_from_cache(m, all_metrics) for m in all_metrics]


async def resolve_enterprise_ids(db: AsyncSession, names: list[str]) -> list[str]:
    """把「企业N」可读名（或企业 id）解析为企业 id；无法解析的丢弃（弃权，不编造）。"""
    if not names:
        return []
    q = select(CoreMetrics.enterprise_id).where(
        or_(
            CoreMetrics.display_name.in_(names),
            CoreMetrics.enterprise_id.in_(names),
        )
    )
    rows = (await db.execute(q)).scalars().all()
    return list(rows)


async def get_legal_events(db: AsyncSession, enterprise_id: str) -> list[dict]:
    await _ensure_cache(db)
    events = _CACHE.get("legal_by_ent", {}).get(enterprise_id, [])
    return [
        {
            "id": ev.id,
            "enterprise_id": ev.enterprise_id,
            "event_type": ev.event_type,
            "severity": ev.severity,
            "amount_involved": float(ev.amount_involved) if ev.amount_involved is not None else None,
            "event_date": ev.event_date.isoformat() if ev.event_date else None,
            "description": ev.description,
            "source": ev.source,
        }
        for ev in events
    ]


async def get_all_warnings(db: AsyncSession) -> list[dict]:
    all_metrics = await _ensure_cache(db)
    items = []
    for m in all_metrics:
        built = _build_from_cache(m, all_metrics)
        if built["warning_signals"]:
            items.append(
                {
                    "enterprise_id": built["enterprise_id"],
                    "display_name": built.get("display_name") or built.get("enterprise_name"),
                    "display_label": built.get("display_label"),
                    "enterprise_name": built.get("display_name") or built.get("enterprise_name"),
                    "industry_l1": built.get("industry_l1"),
                    "risk_level": built["risk_level"],
                    "overall_score": built["overall_score"],
                    "warning_signals": built["warning_signals"],
                }
            )
    return sorted(items, key=lambda x: x["overall_score"])


async def get_slice_attribution(
    db: AsyncSession,
    *,
    industry_l1: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> dict:
    """样本维度归因聚合，供切片报告「为什么」章节。"""
    all_metrics = await _ensure_cache(db)
    subset = [m for m in all_metrics if not industry_l1 or m.industry_l1 == industry_l1]
    if enterprise_ids:
        subset = [m for m in subset if m.enterprise_id in set(enterprise_ids)]
    if not subset:
        return {
            "sample_count": 0,
            "avg_score": 0.0,
            "industry_l1": industry_l1,
            "summary": "暂无样本归因数据。",
            "dimensions": {},
            "drag_factors": [],
        }

    results = [_build_from_cache(m, all_metrics) for m in subset]
    dim_totals = {k: 0.0 for k in DIMENSION_WEIGHTS}
    dim_counts = {k: 0 for k in DIMENSION_WEIGHTS}
    # 拖累因素按「主体数」计：同一主体跨维度重复出现同一 item（如税务健康+法律合规均挂「税务违法」）只计 1 家
    factor_counts: dict[str, int] = {}

    for r in results:
        dims = r.get("dimensions") or {}
        attr = r.get("attribution") or {}
        for key in DIMENSION_WEIGHTS:
            if key in dims:
                dim_totals[key] += float(dims[key])
                dim_counts[key] += 1
        items_this_firm: set[str] = set()
        for dim_data in (attr.get("dimensions") or {}).values():
            for neg in dim_data.get("negative") or []:
                item = str(neg.get("item") or "").strip()
                if item:
                    items_this_firm.add(item)
        for item in items_this_firm:
            factor_counts[item] = factor_counts.get(item, 0) + 1

    dim_avg = {
        key: round(dim_totals[key] / dim_counts[key], 2) if dim_counts[key] else 0.0
        for key in DIMENSION_WEIGHTS
    }
    net_contribution = {
        key: round(dim_avg[key] * DIMENSION_WEIGHTS[key], 2) for key in DIMENSION_WEIGHTS
    }
    sample_n = len(results)
    drag_factors = [
        {"item": item, "count": min(int(cnt), sample_n)}
        for item, cnt in sorted(factor_counts.items(), key=lambda x: -x[1])[:6]
    ]
    avg_overall = sum(float(r.get("overall_score") or 0) for r in results) / len(results)
    weak_dims = [DIMENSION_LABELS[k] for k in DIMENSION_WEIGHTS if dim_avg[k] < 45]

    scope = f"{zh_industry(industry_l1)}行业" if industry_l1 else f"全样本（{len(results)}家）"
    risk = _risk_level(avg_overall)
    if drag_factors:
        top = "、".join(d["item"] for d in drag_factors[:3])
        summary = f"{scope}群体风险判断「{risk}」，高频拖累因素：{top}。"
    elif weak_dims:
        summary = f"{scope}群体风险判断「{risk}」，{'、'.join(weak_dims[:3])}维度整体偏弱。"
    else:
        summary = f"{scope}群体风险判断「{risk}」，各维度表现中等，建议关注核心指标。"

    dimensions = {
        key: {
            "score": dim_avg[key],
            "weight": DIMENSION_WEIGHTS[key],
            "label": DIMENSION_LABELS[key],
            "net_contribution": net_contribution[key],
            **({"coverage": "tax_illegal_only"} if key == "legal" else {}),
        }
        for key in DIMENSION_WEIGHTS
    }
    return {
        "sample_count": len(results),
        "avg_score": round(avg_overall, 2),
        "industry_l1": industry_l1,
        "summary": summary,
        "dimensions": dimensions,
        "drag_factors": drag_factors,
    }


# 行业画像对标：集中度/税负率标量（0=弃权，展示层 ×100）
_PROFILE_FIELDS = [
    ("customer_concentration", "客户集中度"),
    ("supplier_concentration", "供应商集中度"),
    ("category_concentration", "品目集中度"),
    ("vat_burden", "增值税税负率"),
    ("income_tax_burden", "所得税税负率"),
]


def _industry_profile_stats(all_metrics: list[CoreMetrics]) -> list[dict]:
    """各行业画像标量均值（0=弃权剔除，避免把源缺失当成 0 拉低均值）。"""
    groups: dict[str, list[CoreMetrics]] = {}
    for m in all_metrics:
        groups.setdefault(m.industry_l1 or "其他", []).append(m)
    out: list[dict] = []
    for ind, group in groups.items():
        row: dict = {"industry_l1": ind, "n": len(group)}
        for field, _label in _PROFILE_FIELDS:
            vals = [_to_float(getattr(m, field)) for m in group if _to_float(getattr(m, field)) > 0]
            row[field] = round(sum(vals) / len(vals), 4) if vals else None
        out.append(row)
    out.sort(key=lambda x: -x["n"])
    return out


async def get_dashboard_summary(db: AsyncSession) -> dict:
    """工作台聚合：样本数、风险分布、均分、预警数。"""
    all_metrics = await _ensure_cache(db)
    items = [_build_from_cache(m, all_metrics) for m in all_metrics]
    if not items:
        return {
            "sample_count": 0,
            "high_risk_count": 0,
            "avg_score": 0.0,
            "warning_count": 0,
            "risk_distribution": {},
            "industry_profiles": [],
        }

    dist: dict[str, int] = {}
    high = 0
    total = 0.0
    for it in items:
        rl = it.get("risk_level") or "中等风险"
        dist[rl] = dist.get(rl, 0) + 1
        if "高" in rl:
            high += 1
        total += float(it.get("overall_score") or 0)

    warnings = [it for it in items if it.get("warning_signals")]
    return {
        "sample_count": len(items),
        "high_risk_count": high,
        "avg_score": round(total / len(items), 2),
        "warning_count": len(warnings),
        "risk_distribution": dist,
        "industry_profiles": _industry_profile_stats(all_metrics),
        "enterprises": [
            {
                "enterprise_id": it["enterprise_id"],
                "display_name": it.get("display_name") or it.get("enterprise_name"),
                "display_label": it.get("display_label"),
                "risk_level": it.get("risk_level"),
                "overall_score": it.get("overall_score"),
                "industry_l1": it.get("industry_l1"),
            }
            for it in items
        ],
    }


def _group_position(scores: list[float], target_score: float, label: str, value: str) -> dict:
    """给定一组分数与目标分，返回百分位 + 排名 + 偏离度（纯函数，便于单测）。"""
    n = len(scores)
    if n <= 1:
        return {
            "label": label,
            "value": value,
            "peer_total": n,
            "rank": 1,
            "percentile": 50.0,
            "group_mean": round(target_score, 2),
            "deviation": 0.0,
            "score": round(target_score, 2),
        }
    rank = sum(1 for s in scores if s > target_score) + 1
    pct = _percentile(target_score, scores)
    mean = sum(scores) / n
    return {
        "label": label,
        "value": value,
        "peer_total": n,
        "rank": rank,
        "percentile": round(pct, 1),
        "group_mean": round(mean, 2),
        "deviation": round(target_score - mean, 2),
        "score": round(target_score, 2),
    }


async def peer_benchmark(db: AsyncSession, enterprise_id: str) -> dict | None:
    """个体在同行业 / 同地区 / 同规模三组中的 overall_score 百分位 + 排名 + 偏离度。

    用于个体风控分析的「同业基准定位」：把个体放进群体里定位，而非只看绝对分数。
    """
    all_metrics = await _ensure_cache(db)
    target = next((m for m in all_metrics if m.enterprise_id == enterprise_id), None)
    if not target:
        return None

    results = [_build_from_cache(m, all_metrics) for m in all_metrics]
    score_by_id = {r["enterprise_id"]: float(r["overall_score"]) for r in results}
    target_score = score_by_id[enterprise_id]

    def _scores(group_key: str, value: str) -> list[float]:
        peers = [m for m in all_metrics if getattr(m, group_key) == value]
        return sorted(score_by_id[m.enterprise_id] for m in peers if m.enterprise_id in score_by_id)

    return {
        "enterprise_id": enterprise_id,
        "overall_score": round(target_score, 2),
        "groups": {
            "industry": _group_position(_scores("industry_l1", target.industry_l1), target_score, "行业", target.industry_l1),
            "province": _group_position(_scores("province", target.province), target_score, "地区", target.province),
            "scale": _group_position(_scores("scale_label", target.scale_label), target_score, "规模", target.scale_label),
        },
    }
