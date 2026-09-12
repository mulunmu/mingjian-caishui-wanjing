"""
风控分析切片：从 core_metrics / 引擎产出 Claim 列表（算法算数，不经 LLM）
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics, IndustryBenchmark
from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.schemas.semantic_query import QueryType, SemanticQuery
from app.services.intent_engine import IntentResult
from app.services.metric_registry import REVENUE_DEVIATION_WARN, revenue_deviation_warn_label
from app.services.report_templates import business_level, zh_industry, zh_signal
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)

SYNTHESIS_QUERY_IDS = frozenset({"Q_session_synthesis", "Q_session_overall"})
SYNTHESIS_METRICS = frozenset({"session_synthesis_dims", "session_overall_posture"})


def _f(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _claim(
    text: str,
    *,
    metric: str,
    number: float | int | None,
    unit: str,
    table: str,
    field: str,
    query_id: str,
    detail_table: str | None = None,
    evidence: list[str] | None = None,
    confidence: str = "computed",
) -> Claim:
    return Claim(
        claim=text,
        value=ClaimValue(metric=metric, number=number, unit=unit) if number is not None else None,
        trace=ClaimTrace(table=table, field=field, detail_table=detail_table, query_id=query_id),
        confidence=confidence,  # type: ignore[arg-type]
        evidence_chain=evidence or [],
    )


async def _load_metrics(
    db: AsyncSession,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> list[CoreMetrics]:
    q = select(CoreMetrics)
    if industry_l1:
        q = q.where(CoreMetrics.industry_l1 == industry_l1)
    if province:
        q = q.where(CoreMetrics.province == province)
    if enterprise_ids:
        q = q.where(CoreMetrics.enterprise_id.in_(enterprise_ids))
    # 确定性：截断子集（rows[:120] / fraud limit）必须可复现，按主体 ID 稳定排序。
    q = q.order_by(CoreMetrics.enterprise_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def _load_metrics_scoped(
    db: AsyncSession,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> list[CoreMetrics]:
    """按需追加 enterprise_ids 过滤；空时不传该 kwarg，兼容旧测试 monkeypatch 的 _load_metrics 签名。"""
    if enterprise_ids:
        return await _load_metrics(db, industry_l1, province=province, enterprise_ids=enterprise_ids)
    return await _load_metrics(db, industry_l1, province=province)


def is_synthesis_claim(c: Claim) -> bool:
    qid = (c.trace.query_id if c.trace else None) or ""
    metric = (c.value.metric if c.value else None) or ""
    text = (c.claim or "")[:24]
    return (
        qid in SYNTHESIS_QUERY_IDS
        or metric in SYNTHESIS_METRICS
        or text.startswith("会话综合风控分析")
        or text.startswith("会话级综合判断")
    )


def is_synthesis_claim_dict(raw: dict) -> bool:
    trace = raw.get("trace") or {}
    val = raw.get("value") or {}
    qid = trace.get("query_id") or ""
    metric = val.get("metric") or ""
    claim = raw.get("claim") or ""
    return (
        qid in SYNTHESIS_QUERY_IDS
        or metric in SYNTHESIS_METRICS
        or claim.startswith("会话综合风控分析")
        or claim.startswith("会话级综合判断")
    )


def without_synthesis_claims(claims: list[Claim]) -> list[Claim]:
    return [c for c in claims if not is_synthesis_claim(c)]


async def build_trend_industry_claims(
    db: AsyncSession, industry_l1: str | None = None, *, province: str | None = None, enterprise_ids: list[str] | None = None
) -> tuple[list[Claim], dict[str, Any]]:
    rows = await _load_metrics_scoped(db, industry_l1, province=province, enterprise_ids=enterprise_ids)
    if not rows:
        return (
            [
                _claim(
                    "当前样本库暂无可用行业趋势数据。",
                    metric="sample_count",
                    number=0,
                    unit="家",
                    table="core_metrics",
                    field="industry_l1",
                    query_id="Q_trend_industry_empty",
                )
            ],
            {"sample_count": 0},
        )

    by_ind: dict[str, list[CoreMetrics]] = {}
    for m in rows:
        by_ind.setdefault(m.industry_l1 or "其他", []).append(m)

    stats = []
    for ind, group in by_ind.items():
        yoy = [_f(g.revenue_yoy) for g in group]
        avg_yoy = sum(yoy) / len(yoy) if yoy else 0.0
        # 增长/缩减与方向字段同源（revenue_yoy 符号），不再用 social_trend（常为「稳定」/NULL，口径漂移）。
        grow = sum(1 for g in group if _f(g.revenue_yoy) > 0)
        shrink = sum(1 for g in group if _f(g.revenue_yoy) < 0)
        stats.append(
            {
                "industry_l1": ind,
                "n": len(group),
                "avg_revenue_yoy": round(avg_yoy * 100, 2),
                "grow_cnt": grow,
                "shrink_cnt": shrink,
            }
        )
    stats.sort(key=lambda x: x["avg_revenue_yoy"], reverse=True)

    claims: list[Claim] = []
    total = len(rows)
    claims.append(
        _claim(
            f"样本覆盖 {len(stats)} 个行业大类、共 {total} 家匿名主体。",
            metric="sample_count",
            number=total,
            unit="家",
            table="core_metrics",
            field="enterprise_id",
            query_id="Q_trend_industry_count",
            evidence=[f"industry_count={len(stats)}"],
        )
    )
    for s in stats[:6]:
        direction = "上行" if s["avg_revenue_yoy"] > 2 else ("下行" if s["avg_revenue_yoy"] < -2 else "平稳")
        claims.append(
            _claim(
                f"{zh_industry(s['industry_l1'])}行业营收同比均值 {s['avg_revenue_yoy']}%，趋势偏{direction}"
                f"（营收增长 {s['grow_cnt']} / 缩减 {s['shrink_cnt']}，样本 {s['n']}）。",
                metric="avg_revenue_yoy",
                number=s["avg_revenue_yoy"],
                unit="%",
                table="core_metrics",
                field="revenue_yoy",
                query_id="Q_trend_industry_yoy",
                evidence=[f"industry={s['industry_l1']}", f"n={s['n']}"],
            )
        )
    if stats:
        top, bottom = stats[0], stats[-1]
        claims.append(
            _claim(
                f"同比均值最高为{zh_industry(top['industry_l1'])}（{top['avg_revenue_yoy']}%），"
                f"最低为{zh_industry(bottom['industry_l1'])}（{bottom['avg_revenue_yoy']}%）。",
                metric="avg_revenue_yoy_spread",
                number=round(top["avg_revenue_yoy"] - bottom["avg_revenue_yoy"], 2),
                unit="百分点",
                table="core_metrics",
                field="revenue_yoy",
                query_id="Q_trend_industry_spread",
                confidence="inferred",
                evidence=[f"top={top['industry_l1']}", f"bottom={bottom['industry_l1']}"],
            )
        )

    chart = {
        "type": "line",
        "data": {
            "labels": [zh_industry(s["industry_l1"]) for s in stats],
            "series": [{"name": "营收同比%", "values": [s["avg_revenue_yoy"] for s in stats]}],
        },
    }
    return claims, {"industries": stats, "sample_count": total, "charts": chart}


def _score_overall_from_attr(
    attr: dict[str, Any],
    radar_fn: Any,
) -> tuple[list[Claim], dict[str, Any]]:
    """六维 overall 章：从 get_slice_attribution 结果装配 claim + 雷达。"""
    dims = attr.get("dimensions") or {}
    claims = [
        _claim(
            attr["summary"],
            metric="avg_score",
            number=attr.get("avg_score"),
            unit="分",
            table="assessment",
            field="overall_score",
            query_id="Q_score_overall",
            evidence=[f"sample_count={attr.get('sample_count')}"],
        )
    ]
    for key, d in dims.items():
        claims.append(
            _claim(
                f"「{d.get('label', key)}」维度表现{business_level(float(d.get('score') or 0))}。",
                metric=f"dim_{key}",
                number=round(float(d.get("score") or 0), 2),
                unit="分",
                table="assessment",
                field=f"dim_{key}",
                query_id=f"Q_score_dim_{key}",
                evidence=[f"weight={d.get('weight')}"],
            )
        )
    radar = radar_fn(attr)
    meta: dict[str, Any] = {
        "attribution": attr,
        "sample_count": attr.get("sample_count"),
    }
    if radar:
        meta["charts"] = radar
    return claims, meta


async def build_score_claims(
    db: AsyncSession,
    industry_l1: str | None = None,
    dimension: str = "overall",
    *,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> tuple[list[Claim], dict[str, Any]]:
    # overall：六维归因必须同源当前筛选子集（禁止有行业筛选却回落全库 193）
    if dimension == "overall":
        from app.services import assessment
        from app.services.chart_payloads import attribution_radar_chart

        attr = await assessment.get_slice_attribution(
            db, industry_l1=industry_l1, enterprise_ids=enterprise_ids
        )
        # 地区筛选：归因暂无 province 参数时，用 scoped 行数校验；不一致则弃权回落到行聚合
        if province:
            scoped = await _load_metrics_scoped(
                db, industry_l1, province=province, enterprise_ids=enterprise_ids
            )
            if int(attr.get("sample_count") or 0) != len(scoped):
                # province 未进归因：走下方行聚合路径，保证 sample_count 对齐
                pass
            else:
                dims = attr.get("dimensions") or {}
                if dims and attr.get("summary"):
                    return _score_overall_from_attr(attr, attribution_radar_chart)
        else:
            dims = attr.get("dimensions") or {}
            if dims and attr.get("summary"):
                return _score_overall_from_attr(attr, attribution_radar_chart)

    rows = await _load_metrics_scoped(
        db,
        industry_l1,
        province=province,
        enterprise_ids=enterprise_ids,
    )
    if not rows:
        return (
            [
                _claim(
                    "暂无评分样本。",
                    metric="sample_count",
                    number=0,
                    unit="家",
                    table="core_metrics",
                    field="credit_score",
                    query_id="Q_score_empty",
                )
            ],
            {},
        )

    # overall 兜底（归因不可用 / 含 province 未进归因）：信用均分，sample_count=scoped N
    if dimension == "overall":
        avg = sum(_f(g.credit_score) for g in rows) / len(rows)
        on_time_vals = [_f(g.tax_on_time_rate) for g in rows if _f(g.tax_on_time_rate) > 0]
        on_time = (sum(on_time_vals) / len(on_time_vals)) if on_time_vals else 0.0
        scope = zh_industry(industry_l1) or "当前范围"
        claims = [
            _claim(
                f"{scope}综合经营表现{business_level(avg)}，信用均分 {avg:.1f}"
                + (f"，纳税准时率均值 {on_time * 100:.1f}%" if on_time else "")
                + f"（样本 {len(rows)} 家）。",
                metric="avg_credit_score",
                number=round(avg, 2),
                unit="分",
                table="core_metrics",
                field="credit_score",
                query_id="Q_score_overall_scoped",
                evidence=[f"n={len(rows)}"],
            )
        ]
        return claims, {"sample_count": len(rows)}

    if dimension == "industry" or (not industry_l1 and dimension != "region"):
        by_ind: dict[str, list[CoreMetrics]] = {}
        for m in rows:
            by_ind.setdefault(m.industry_l1 or "其他", []).append(m)
        claims = []
        payload = []
        on_time_series = []
        for ind, group in sorted(by_ind.items(), key=lambda x: -len(x[1])):
            avg = sum(_f(g.credit_score) for g in group) / len(group)
            on_time = sum(_f(g.tax_on_time_rate) for g in group) / len(group)
            on_time_series.append(round(on_time * 100, 1))
            small_n = len(group) < 5
            note = "（样本 <5，仅供参考，不作判断依据）" if small_n else ""
            payload.append({"industry_l1": ind, "n": len(group), "avg_credit_score": round(avg, 2)})
            claims.append(
                _claim(
                    f"{zh_industry(ind) or ind}行业信用表现{business_level(avg)}，"
                    f"纳税准时率均值 {on_time * 100:.1f}%（样本 {len(group)}）{note}",
                    metric="avg_credit_score",
                    number=round(avg, 2),
                    unit="分",
                    table="core_metrics",
                    field="credit_score",
                    query_id="Q_score_industry",
                    confidence="inferred" if small_n else "computed",
                    evidence=[f"tax_on_time_rate_avg={round(on_time, 4)}", f"n={len(group)}"],
                )
            )
        chart = {
            "type": "bar",
            "data": {
                "labels": [p["industry_l1"] for p in payload],
                "series": [
                    {"name": "信用表现", "values": [p["avg_credit_score"] for p in payload]},
                    {"name": "纳税准时率%", "values": on_time_series},
                ],
            },
        }
        return claims, {"by_industry": payload, "sample_count": len(rows), "charts": chart}

    # region：地区间评分对比（含对比图 + 最高/最低对比结论）
    by_prov: dict[str, list[CoreMetrics]] = {}
    for m in rows:
        by_prov.setdefault(m.province or "未知", []).append(m)
    region_stats = []
    for prov, group in by_prov.items():
        avg = sum(_f(g.credit_score) for g in group) / len(group)
        region_stats.append({"province": prov, "n": len(group), "avg": round(avg, 2)})
    region_stats.sort(key=lambda x: x["avg"], reverse=True)

    claims = []
    for s in region_stats[:8]:
        # 结论导向：不在用户面堆「样本 n / 仅供参考」meta；小样本仍标 confidence=inferred 供机检
        small_n = s["n"] < 5
        claims.append(
            _claim(
                f"{s['province']}地区信用表现{business_level(s['avg'])}，均分 {s['avg']:.1f}",
                metric="avg_credit_score",
                number=s["avg"],
                unit="分",
                table="core_metrics",
                field="credit_score",
                query_id="Q_score_region",
                confidence="inferred" if small_n else "computed",
                evidence=[f"province={s['province']}", f"n={s['n']}"],
            )
        )
    if len(region_stats) >= 2:
        top, bottom = region_stats[0], region_stats[-1]
        claims.append(
            _claim(
                f"地区对比：{top['province']}最高（{top['avg']:.1f}分），{bottom['province']}最低"
                f"（{bottom['avg']:.1f}分），相差 {round(top['avg'] - bottom['avg'], 2)} 分。",
                metric="avg_credit_score_spread",
                number=round(top["avg"] - bottom["avg"], 2),
                unit="分",
                table="core_metrics",
                field="credit_score",
                query_id="Q_score_region_spread",
                confidence="inferred",
                evidence=[f"top={top['province']}", f"bottom={bottom['province']}"],
            )
        )
    # 地区过多时：图用 Top/Bottom 合并，避免横轴标签挤压；完整名单仍在 claims/表
    chart_stats = region_stats
    if len(region_stats) > 12:
        top_n, bottom_n = region_stats[:6], region_stats[-4:]
        mid = region_stats[6:-4]
        mid_avg = round(sum(s["avg"] for s in mid) / len(mid), 2) if mid else None
        chart_stats = list(top_n)
        if mid_avg is not None:
            chart_stats.append({"province": f"其余{len(mid)}地", "n": sum(s["n"] for s in mid), "avg": mid_avg})
        # 避免 bottom 与 top 重叠
        top_set = {s["province"] for s in top_n}
        for s in bottom_n:
            if s["province"] not in top_set:
                chart_stats.append(s)
    chart = {
        "type": "bar",
        "orientation": "horizontal" if len(chart_stats) > 8 else "vertical",
        "data": {
            "labels": [s["province"] for s in chart_stats],
            "series": [{"name": "信用表现", "values": [s["avg"] for s in chart_stats]}],
        },
    }
    return claims, {"region_stats": region_stats, "region_count": len(by_prov), "sample_count": len(rows), "charts": chart}


async def build_benchmark_claims(
    db: AsyncSession, industry_l1: str | None = None, *, province: str | None = None, enterprise_ids: list[str] | None = None
) -> tuple[list[Claim], dict]:
    q = select(IndustryBenchmark)
    if industry_l1:
        q = q.where(IndustryBenchmark.industry_l1 == industry_l1)
    result = await db.execute(q)
    benches = list(result.scalars().all())
    if not benches:
        # fallback aggregate from core_metrics
        return await build_score_claims(db, industry_l1, dimension="industry", province=province, enterprise_ids=enterprise_ids)

    claims = []
    for b in benches:
        # 小样本采信阈值：样本 <5 的基准均值仅供参考，不作判断依据（弃权优先于编造）。
        small_n = int(getattr(b, "sample_count", 0) or 0) < 5
        claims.append(
            _claim(
                f"{zh_industry(b.industry_l1)}行业基准：信用表现{business_level(_f(b.avg_credit_score))}，"
                f"营收偏差均值 {_f(b.avg_revenue_deviation) * 100:.2f}%，"
                f"高风险占比 {_f(b.high_risk_rate) * 100:.1f}%",
                metric="avg_credit_score",
                number=round(_f(b.avg_credit_score), 2),
                unit="分",
                table="industry_benchmark",
                field="avg_credit_score",
                query_id="Q_benchmark_industry",
                confidence="inferred" if small_n else "computed",
                evidence=[
                    f"avg_revenue_deviation={_f(b.avg_revenue_deviation)}",
                    f"high_risk_rate={_f(b.high_risk_rate)}",
                    f"sample_count={b.sample_count}",
                ],
            )
        )
    payload = [{"industry_l1": b.industry_l1, "avg_credit_score": round(_f(b.avg_credit_score), 2)} for b in benches]
    rows = await _load_metrics_scoped(db, industry_l1, province=province, enterprise_ids=enterprise_ids)
    live_by_ind: dict[str, list[float]] = {}
    for m in rows:
        live_by_ind.setdefault(m.industry_l1 or "其他", []).append(_f(m.credit_score))
    live_avgs = {k: round(sum(v) / len(v), 2) for k, v in live_by_ind.items() if v}
    labels = [zh_industry(p["industry_l1"]) for p in payload]
    chart = {
        "type": "bar",
        "data": {
            "labels": labels,
            "series": [
                {"name": "行业基准", "values": [p["avg_credit_score"] for p in payload]},
                {"name": "样本均值", "values": [live_avgs.get(l, 0) for l in labels]},
            ],
        },
    }
    return claims, {"benchmarks": len(benches), "charts": chart}


async def build_financial_claims(
    db: AsyncSession,
    industry_l1: str | None = None,
    dimension: str = "overall",
    *,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> tuple[list[Claim], dict[str, Any]]:
    """聚合「财务健康」切片：四能力比率均值 + 客观评级（阈值统一自 financial_benchmarks，铁律 L1）。

    比率 0=弃权：仅对非 0 样本求均值，不产「无数据」假结论。
    """
    from app.services.financial_benchmarks import (
        FINANCIAL_GROUPS,
        FINANCIAL_RATIOS,
        assess_financial_ratio,
        format_financial_ratio,
    )

    rows = await _load_metrics_scoped(db, industry_l1, province=province, enterprise_ids=enterprise_ids)
    if not rows:
        return (
            [
                _claim(
                    "当前样本库暂无财务数据。",
                    metric="sample_count", number=0, unit="家",
                    table="core_metrics", field="has_financial_statements",
                    query_id="Q_financial_empty",
                )
            ],
            {"sample_count": 0},
        )

    coverage = sum(1 for m in rows if bool(m.has_financial_statements))
    claims = [
        _claim(
            f"样本 {len(rows)} 家，其中 {coverage} 家具备完整三大报表"
            f"（财务覆盖率 {coverage / len(rows) * 100:.1f}%）。",
            metric="financial_coverage", number=coverage, unit="家",
            table="core_metrics", field="has_financial_statements",
            query_id="Q_financial_coverage",
            evidence=[f"sample_count={len(rows)}"],
        )
    ]

    group_pass_rate: list[dict[str, Any]] = []
    for gname in FINANCIAL_GROUPS:
        fields = [f for f, cfg in FINANCIAL_RATIOS.items() if cfg.get("group") == gname]
        rated: list[dict[str, Any]] = []
        for field in fields:
            vals = [_f(getattr(m, field)) for m in rows if _f(getattr(m, field)) != 0.0]
            if not vals:
                continue  # 0=弃权，不产假结论
            avg = sum(vals) / len(vals)
            rating = assess_financial_ratio(field, avg)
            cfg = FINANCIAL_RATIOS[field]
            is_pct = cfg.get("is_pct")
            num = round(avg * 100, 2) if is_pct else round(avg, 2)
            rated.append({"field": field, "rating": rating})
            claims.append(
                _claim(
                    f"{cfg['label']}均值 {format_financial_ratio(field, avg)}"
                    f"（{rating}，样本 {len(vals)}）。",
                    metric=field, number=num, unit=cfg.get("unit") or "",
                    table="core_metrics", field=field,
                    query_id=f"Q_financial_{field}",
                    evidence=[f"group={gname}", f"n={len(vals)}"],
                )
            )
        if rated:
            pass_cnt = sum(1 for r in rated if r["rating"] == "达标")
            group_pass_rate.append({
                "group": gname,
                "pass_rate": round(pass_cnt / len(rated) * 100, 1),
            })

    chart = None
    if group_pass_rate:
        chart = {
            "type": "bar",
            "data": {
                "labels": [g["group"] for g in group_pass_rate],
                "series": [
                    {"name": "达标率%", "values": [g["pass_rate"] for g in group_pass_rate]}
                ],
            },
        }
    return claims, {
        "sample_count": len(rows),
        "financial_coverage": coverage,
        "group_pass_rate": group_pass_rate,
        "charts": chart,
    }


async def build_tax_claims(
    db: AsyncSession,
    industry_l1: str | None = None,
    dimension: str = "overall",
    *,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> tuple[list[Claim], dict[str, Any]]:
    """聚合「税务合规」切片：纳税准时率 / 税负率 / 欠税 / 违法 / 滞纳。0=弃权口径。"""
    rows = await _load_metrics_scoped(db, industry_l1, province=province, enterprise_ids=enterprise_ids)
    if not rows:
        return (
            [
                _claim(
                    "当前样本库暂无税务数据。",
                    metric="sample_count", number=0, unit="家",
                    table="core_metrics", field="tax_on_time_rate",
                    query_id="Q_tax_empty",
                )
            ],
            {"sample_count": 0},
        )

    def _mean(field: str) -> tuple[float, int]:
        vals = [_f(getattr(m, field)) for m in rows if _f(getattr(m, field)) != 0.0]
        if not vals:
            return 0.0, 0
        return sum(vals) / len(vals), len(vals)

    on_time, n_on = _mean("tax_on_time_rate")
    vat, n_vat = _mean("vat_burden")
    income, n_income = _mean("income_tax_burden")
    arrears = sum(1 for m in rows if int(getattr(m, "tax_arrears_cnt", 0) or 0) > 0)
    viol = sum(1 for m in rows if int(getattr(m, "tax_violation_cnt", 0) or 0) > 0)
    late = sum(int(getattr(m, "tax_late_penalty_cnt", 0) or 0) for m in rows)

    claims = []
    if n_on > 0:
        claims.append(
            _claim(
                f"样本 {len(rows)} 家，纳税准时率均值 {on_time * 100:.1f}%（有效 {n_on} 家）。",
                metric="tax_on_time_rate", number=round(on_time * 100, 2), unit="%",
                table="core_metrics", field="tax_on_time_rate",
                query_id="Q_tax_on_time", evidence=[f"n={n_on}"],
            )
        )
    else:
        claims.append(
            _claim(
                f"样本 {len(rows)} 家，纳税准时率无有效观测（0=弃权）。",
                metric="tax_on_time_rate", number=None, unit="%",
                table="core_metrics", field="tax_on_time_rate",
                query_id="Q_tax_on_time_abstain", evidence=["n=0"],
                confidence="inferred",
            )
        )
    if n_vat > 0 or n_income > 0:
        parts = []
        if n_vat > 0:
            parts.append(f"增值税税负率均值 {vat * 100:.2f}%（有效 {n_vat} 家）")
        else:
            parts.append("增值税税负率无有效观测")
        if n_income > 0:
            parts.append(f"所得税税负率均值 {income * 100:.2f}%（有效 {n_income} 家）")
        else:
            parts.append("所得税税负率无有效观测")
        claims.append(
            _claim(
                "，".join(parts) + "。",
                metric="vat_burden",
                number=round(vat * 100, 2) if n_vat > 0 else None,
                unit="%",
                table="core_metrics", field="vat_burden",
                query_id="Q_tax_burden",
                evidence=[f"n_vat={n_vat}", f"n_income={n_income}"],
            )
        )
    claims.append(
        _claim(
            f"欠税主体 {arrears} 家，税务违法主体 {viol} 家，滞纳/罚款累计 {late} 笔。",
            metric="tax_arrears_cnt", number=arrears, unit="家",
            table="core_metrics", field="tax_arrears_cnt",
            query_id="Q_tax_arrears",
            evidence=[f"tax_violation_cnt={viol}", f"tax_late_penalty_cnt={late}"],
        )
    )
    chart_labels = []
    chart_values = []
    if n_on > 0:
        chart_labels.append("纳税准时率")
        chart_values.append(round(on_time * 100, 1))
    if n_vat > 0:
        chart_labels.append("增值税税负")
        chart_values.append(round(vat * 100, 2))
    if n_income > 0:
        chart_labels.append("所得税税负")
        chart_values.append(round(income * 100, 2))
    chart = {
        "type": "bar",
        "data": {
            "labels": chart_labels or ["无有效比率"],
            "series": [{"name": "%", "values": chart_values or [0]}],
        },
    } if chart_labels else None
    return claims, {
        "sample_count": len(rows),
        "on_time_avg": on_time if n_on else None,
        "vat_burden_avg": vat if n_vat else None,
        "income_tax_avg": income if n_income else None,
        "arrears_cnt": arrears,
        "violation_cnt": viol,
        "late_penalty_cnt": late,
        "charts": chart,
    }


async def build_signal_claims(
    db: AsyncSession,
    *,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> tuple[list[Claim], dict]:
    rows = await _load_metrics_scoped(
        db, industry_l1, province=province, enterprise_ids=enterprise_ids
    )
    # 源库无失信/被执行表：不报恒为 0 的假覆盖；仅用税务侧可得信号
    high_dev = [m for m in rows if _f(m.revenue_deviation) >= REVENUE_DEVIATION_WARN]
    low_credit = [m for m in rows if (m.credit_level or "") in ("C", "D", "M")]
    tax_viol = [m for m in rows if int(getattr(m, "tax_violation_cnt", 0) or 0) > 0]

    # 互斥分桶（优先级：税务违法 > 营收偏差 > 信用等级），避免饼图/总数双计数
    bucket_tax: set[str] = set()
    bucket_dev: set[str] = set()
    bucket_credit: set[str] = set()
    for m in rows:
        eid = m.enterprise_id
        if int(getattr(m, "tax_violation_cnt", 0) or 0) > 0:
            bucket_tax.add(eid)
        elif _f(m.revenue_deviation) >= REVENUE_DEVIATION_WARN:
            bucket_dev.add(eid)
        elif (m.credit_level or "") in ("C", "D", "M"):
            bucket_credit.add(eid)
    unique_affected = bucket_tax | bucket_dev | bucket_credit

    # 多重风险叠加：按原始信号逐主体计命中类数（与互斥分桶独立，避免双计数混淆）。
    # 三类 = 税务违法 / 营收偏差≥阈值 / 信用等级 C/D/M。
    multi_2 = 0
    multi_3 = 0
    for m in rows:
        hits = 0
        if int(getattr(m, "tax_violation_cnt", 0) or 0) > 0:
            hits += 1
        if _f(m.revenue_deviation) >= REVENUE_DEVIATION_WARN:
            hits += 1
        if (m.credit_level or "") in ("C", "D", "M"):
            hits += 1
        if hits >= 2:
            multi_2 += 1
        if hits >= 3:
            multi_3 += 1

    claims = [
        _claim(
            f"样本 {len(rows)} 家中，至少命中一类风险信号的主体共 {len(unique_affected)} 家；"
            f"其中税务违法 {len(tax_viol)}、{revenue_deviation_warn_label()} {len(high_dev)}、信用等级 C/D/M {len(low_credit)}"
            f"（三类可重叠，饼图按优先级互斥展示）。"
            f"（法律合规维度仅覆盖税务侧，不含失信/被执行/诉讼）",
            metric="signal_total",
            number=len(unique_affected),
            unit="家",
            table="core_metrics",
            field="tax_violation_cnt",
            query_id="Q_signal_overview",
            evidence=[
                "coverage=tax_illegal_only",
                f"tax_violation={len(tax_viol)}",
                f"high_dev={len(high_dev)}",
                f"low_credit={len(low_credit)}",
                f"unique_affected={len(unique_affected)}",
                f"multi_hit_ge2={multi_2}",
                f"multi_hit_ge3={multi_3}",
            ],
        )
    ]
    if multi_2:
        claims.append(
            _claim(
                f"同时命中 ≥2 类风险 {multi_2} 家、≥3 类 {multi_3} 家（多重风险叠加，需优先复核）。",
                metric="multi_hit_count",
                number=multi_2,
                unit="家",
                table="core_metrics",
                field="tax_violation_cnt",
                query_id="Q_signal_multi_hit",
                confidence="inferred",
                evidence=[f"ge2={multi_2}", f"ge3={multi_3}", "口径=原始信号逐主体计数（非互斥分桶）"],
            )
        )
    if low_credit:
        by_ind: dict[str, int] = {}
        for m in low_credit:
            by_ind[m.industry_l1 or "其他"] = by_ind.get(m.industry_l1 or "其他", 0) + 1
        top_ind = max(by_ind.items(), key=lambda x: x[1])
        claims.append(
            _claim(
                f"低信用等级主体最多集中在{top_ind[0]}行业（{top_ind[1]} 家）。",
                metric="low_credit_industry_count",
                number=top_ind[1],
                unit="家",
                table="core_metrics",
                field="credit_level",
                query_id="Q_signal_credit_industry",
                confidence="inferred",
            )
        )
    meta = {
        "sample_count": len(rows),
        "coverage": "tax_illegal_only",
        "tax_violation": len(tax_viol),
        "high_dev": len(high_dev),
        "low_credit": len(low_credit),
        "multi_hit_ge2": multi_2,
        "multi_hit_ge3": multi_3,
        "unique_affected": sorted(unique_affected),
    }
    from app.services.chart_payloads import signal_funnel_chart, signal_industry_heatmap, signal_pie_chart

    heatmap = signal_industry_heatmap(rows)
    if heatmap:
        meta["charts"] = heatmap
    elif unique_affected:
        meta["charts"] = signal_funnel_chart(len(rows), bucket_tax, bucket_dev, bucket_credit)
    else:
        meta["charts"] = signal_pie_chart(bucket_tax, bucket_dev, bucket_credit)
    return claims, meta


async def build_authenticity_claims(
    db: AsyncSession, industry_l1: str | None = None, *, province: str | None = None, enterprise_ids: list[str] | None = None
) -> tuple[list[Claim], dict]:
    from app.services import authenticity_engine

    rows = await _load_metrics_scoped(db, industry_l1, province=province, enterprise_ids=enterprise_ids)
    if not rows:
        return (
            [
                _claim(
                    "暂无真实性分析样本。",
                    metric="sample_count",
                    number=0,
                    unit="家",
                    table="core_metrics",
                    field="revenue_deviation",
                    query_id="Q_auth_empty",
                )
            ],
            {},
        )

    # Benford 已改用本切片金额（PG，无 MySQL 依赖），无需截断：分析全 scoped 主体，
    # 消除「120 vs 193」口径漂移。行序已由 _load_metrics 的 ORDER BY 确定。
    sample = rows
    result = await run_blocking(
        authenticity_engine.analyze_authenticity_batch, sample, industry_l1=industry_l1
    )
    claims = [
        _claim(
            f"{zh_industry(result['industry_l1']) or '全部'}主体 {result['sample_count']} 家，"
            f"其中 {result['suspicious_count']} 家（占比 {result['suspicious_rate'] * 100:.1f}%）"
            f"申报、开票、财报多口径营收不一致，建议核对申报与开票数据差异，关注收入真实性。",
            metric="suspicious_count",
            number=result["suspicious_count"],
            unit="家",
            table="core_metrics",
            field="revenue_deviation",
            query_id="Q_authenticity_industry_slice",
            evidence=[f"avg_cross_deviation={result.get('avg_cross_deviation')}"],
        )
    ]
    bf = result.get("benford") or {}
    if bf.get("n"):
        chi2 = bf.get("chi2")
        n = bf.get("n")
        scope = zh_industry(result.get("industry_l1")) or "全部主体"
        if chi2 is None:
            # 样本不足（弃权优先于编造）：只给业务说明，不输出统计量
            claims.append(
                _claim(
                    f"{scope}开票金额样本量不足（{n} 家），暂无法判断开票金额分布是否异常。",
                    metric="benford_mad",
                    number=None,
                    unit="",
                    table="syx_tax_finance_profit_year",
                    field="current_year_accumulative_amount",
                    detail_table="syx_invoice",
                    query_id="Q_benford",
                    evidence=[f"n={n}"],
                )
            )
        elif bf.get("violation"):
            claims.append(
                _claim(
                    f"{scope}开票金额首位数字分布异常，偏离自然分布规律，"
                    f"存在人为操纵开票金额的嫌疑，建议核实相关票据的真实性。",
                    metric="benford_mad",
                    number=n,
                    unit="家",
                    table="syx_tax_finance_profit_year",
                    field="current_year_accumulative_amount",
                    detail_table="syx_invoice",
                    query_id="Q_benford",
                    evidence=[f"n={n}", f"violation={bf.get('violation')}"],
                )
            )
        else:
            claims.append(
                _claim(
                    f"{scope}开票金额首位数字分布正常，未见明显人为操纵迹象。",
                    metric="benford_mad",
                    number=n,
                    unit="家",
                    table="syx_tax_finance_profit_year",
                    field="current_year_accumulative_amount",
                    detail_table="syx_invoice",
                    query_id="Q_benford",
                    evidence=[f"n={n}", f"violation={bf.get('violation')}"],
                )
            )
    ok_count = max(0, result["sample_count"] - result["suspicious_count"])
    result["charts"] = {
        "type": "pie",
        "data": {
            "labels": ["可疑主体", "正常主体"],
            "series": [{"name": "家数", "values": [result["suspicious_count"], ok_count]}],
        },
    }
    return claims, result


async def build_fraud_claims(
    db: AsyncSession, industry_l1: str | None = None, limit: int | None = None, *, province: str | None = None, enterprise_ids: list[str] | None = None
) -> tuple[list[Claim], dict]:
    from app.services import fraud_engine

    q = select(
        CoreMetrics.enterprise_id,
        CoreMetrics.display_label,
        CoreMetrics.industry_l1,
        CoreMetrics.province,
        CoreMetrics.display_name,
    )
    if industry_l1:
        q = q.where(CoreMetrics.industry_l1 == industry_l1)
    if province:
        q = q.where(CoreMetrics.province == province)
    if enterprise_ids:
        q = q.where(CoreMetrics.enterprise_id.in_(enterprise_ids))
    # 口径统一：舞弊特征走 PG 预计算（engine_features_store），无需截断，
    # 与封面 KPI（_resolve_scenario_kpis）同取全 scoped 主体，消除 40 vs 60 漂移。
    q = q.order_by(CoreMetrics.enterprise_id)
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    rows = [(r[0], r[1], r[2], r[4]) for r in result.all()]
    if not rows:
        return (
            [
                _claim(
                    "暂无舞弊分析样本。",
                    metric="sample_count",
                    number=0,
                    unit="家",
                    table="syx_invoice_details",
                    field="scbm",
                    query_id="Q_fraud_empty",
                )
            ],
            {},
        )

    try:
        out = await run_blocking(fraud_engine.analyze_metrics_batch, rows, max_n=limit)
    except Exception as exc:
        logger.warning("fraud slice failed: %s", exc)
        return (
            [
                _claim(
                    "舞弊引擎暂时不可用，请稍后重试或改问行业趋势。",
                    metric="error",
                    number=None,
                    unit="",
                    table="syx_invoice_details",
                    field="scbm",
                    query_id="Q_fraud_error",
                    confidence="inferred",
                )
            ],
            {"error": str(exc)},
        )

    if out.get("sample_count", 0) == 0 and rows:
        miss_n = out.get("precompute_miss") or len(rows)
        return (
            [
                _claim(
                    "发票舞弊特征数据暂未就绪，本报告暂不评估发票舞弊风险。",
                    metric="precompute_missing",
                    number=None,
                    unit="",
                    table="enterprise_engine_features",
                    field="fraud_composite_score",
                    query_id="Q_fraud_precompute_miss",
                    confidence="inferred",
                    evidence=[f"requested={len(rows)}", f"coverage=precompute_missing"],
                )
            ],
            out,
        )

    claims = [
        _claim(
            f"{zh_industry(out['industry_l1']) or '全部'}主体 {out['sample_count']} 家，"
            f"其中 {out['flagged_count']} 家存在进销错配、红字发票异常等发票舞弊迹象，"
            f"建议核查票据交易背景与货物凭证。",
            metric="flagged_count",
            number=out["flagged_count"],
            unit="家",
            table="syx_invoice_details",
            field="scbm",
            detail_table="syx_invoice",
            query_id="Q_fraud_industry_slice",
            evidence=[f"signals={out.get('signal_counts')}"],
        )
    ]
    for sig, cnt in list((out.get("signal_counts") or {}).items())[:5]:
        claims.append(
            _claim(
                f"信号「{zh_signal(sig)}」命中 {cnt} 家主体。",
                metric="signal_count",
                number=cnt,
                unit="家",
                table="syx_invoice_details",
                field="scbm",
                query_id="Q_fraud_signal",
                evidence=["口径=去重主体数（signal_counts 为命中主体数，非事件次数）"],
            )
        )
    sc = out.get("signal_counts") or {}
    if sc:
        labels = [zh_signal(k) for k in sc.keys()]
        values = list(sc.values())
        if len(labels) >= 2:
            out["charts"] = {
                "type": "funnel",
                "data": {"labels": labels, "values": values},
            }
        else:
            out["charts"] = {
                "type": "bar",
                "data": {
                    "labels": labels,
                    "series": [{"name": "信号次数", "values": values}],
                },
            }
    return claims, out


ANALYSIS_FUNCTIONS = frozenset(
    {"trend", "authenticity", "fraud", "score", "benchmark", "signal", "financial", "tax"}
)
RISK_FUNCTIONS = frozenset({"signal", "fraud"})
FUNCTION_LABELS = {
    "trend": "趋势",
    "authenticity": "真实性",
    "fraud": "舞弊",
    "score": "评分",
    "benchmark": "基准",
    "signal": "预警",
}


def _build_overall_judgment(covered: list[str], headlines: dict[str, str]) -> Claim | None:
    """会话级 overall judgment：≥3 维已覆盖时给出风险倾向与行动建议。"""
    if len(covered) < 3:
        return None
    risk_hits = [fn for fn in covered if fn in RISK_FUNCTIONS]
    if len(risk_hits) >= 2:
        posture, action = "偏高", "优先复核预警主体并下钻行业"
    elif risk_hits:
        posture, action = "中等偏上", "结合评分/真实性交叉验证预警样本"
    elif "score" in covered and "benchmark" in covered:
        posture, action = "中等", "关注低于基准的行业并跟踪趋势"
    else:
        posture, action = "待进一步交叉", "建议补全舞弊或预警维度后出报告"

    lead = risk_hits[0] if risk_hits else covered[0]
    lead_text = headlines.get(lead, "")[:48]
    return _claim(
        f"会话级综合判断：已交叉 {len(covered)} 个风控维度（{'、'.join(FUNCTION_LABELS.get(f, f) for f in covered[:4])}），"
        f"整体风险倾向{posture}。"
        f"{'预警/舞弊信号占主导' if risk_hits else f'当前以{FUNCTION_LABELS.get(lead, lead)}为主'}（{lead_text}…）。"
        f"建议{action}。",
        metric="session_overall_posture",
        number=len(covered),
        unit="维",
        table="conclusion_store",
        field="function",
        query_id="Q_session_overall",
        confidence="inferred",
        evidence=[f"functions={covered}", f"risk_functions={risk_hits}"],
    )


def build_session_synthesis_claims(
    session_id: str,
    *,
    pending_function: str | None = None,
    pending_claims: list[Claim] | None = None,
) -> tuple[list[Claim], dict]:
    """跨维综合风控分析：会话内多 function 结论汇总为一条 synthesis。"""
    from app.services import conclusion_store

    headlines: dict[str, str] = {}
    for item in conclusion_store.list_session_conclusions(session_id):
        fn = item.get("function")
        if fn not in ANALYSIS_FUNCTIONS:
            continue
        for raw in item.get("claims") or []:
            if is_synthesis_claim_dict(raw):
                continue
            text = (raw.get("claim") or "").strip()
            if text and raw.get("confidence") != "asserted":
                headlines[fn] = text
                break

    if pending_function in ANALYSIS_FUNCTIONS and pending_claims:
        for c in without_synthesis_claims(pending_claims):
            if c.confidence != "asserted" and (c.claim or "").strip():
                headlines[pending_function] = c.claim.strip()
                break

    covered = sorted(headlines.keys())
    if len(covered) < 2:
        return [], {}

    parts = [f"{FUNCTION_LABELS.get(fn, fn)}：{headlines[fn][:72]}" for fn in covered[:4]]
    claim = _claim(
        f"会话综合风控分析（已覆盖 {len(covered)} 维）：" + "；".join(parts) + "。",
        metric="session_synthesis_dims",
        number=len(covered),
        unit="维",
        table="conclusion_store",
        field="function",
        query_id="Q_session_synthesis",
        confidence="inferred",
        evidence=[f"functions={covered}"],
    )
    claims = [claim]
    overall = _build_overall_judgment(covered, headlines)
    if overall:
        claims.append(overall)
    return claims, {"synthesis_functions": covered, "synthesis": True, "overall_judgment": overall is not None}


WARNING_SIGNAL_LABELS = {
    "tax_on_time_rate_low": "纳税准时率偏低",
    "invoice_monthly_avg_drop": "月均开票额骤降",
    "credit_level_risk": "信用等级 C/D/M",
    "social_trend_shrink": "社保趋势缩减",
    "revenue_deviation_high": "营收偏差过高",
    "legal_compliance_risk": "法律合规分偏低",
    "legal_enforcement_risk": "失信/被执行",
}

ENTERPRISE_FOLLOWUPS = [
    "生成个体深度报告",
    "它在同行业的排名是多少？",
    "有哪些风险成因与预警信号？",
]


async def build_enterprise_claims(
    db: AsyncSession, enterprise_id: str
) -> tuple[list[Claim], dict[str, Any]]:
    """个体深度风控分析：单一样本画像结论（computed，数字可溯源，不经 LLM）。"""
    from app.services import assessment
    from app.services.assessment_weights import DIMENSION_WEIGHTS
    from app.services.chart_payloads import enterprise_radar_chart

    profile = await assessment.calculate(db, enterprise_id)
    if not profile:
        return (
            [
                _claim(
                    "未找到该匿名样本，请回到风控工作台重新选择预警主体。",
                    metric="sample_count",
                    number=0,
                    unit="家",
                    table="core_metrics",
                    field="enterprise_id",
                    query_id="Q_enterprise_not_found",
                    confidence="inferred",
                )
            ],
            {"enterprise_id": enterprise_id},
        )

    name = profile.get("display_name") or profile.get("enterprise_name") or profile.get("display_label") or "样本"
    claims: list[Claim] = []

    claims.append(
        _claim(
            f"{name}综合风险等级「{profile['risk_level']}」，"
            f"所属 {zh_industry(profile.get('industry_l1')) or '未知'} · "
            f"{profile.get('province') or '未知'}。",
            metric="overall_score",
            number=profile["overall_score"],
            unit="分",
            table="assessment",
            field="overall_score",
            query_id="Q_enterprise_overall",
            evidence=[f"risk_level={profile['risk_level']}"],
        )
    )

    dim_details = profile.get("dimension_details") or {}
    dims = profile.get("dimensions") or {}
    for key in DIMENSION_WEIGHTS:
        score = dims.get(key)
        if score is None:
            continue
        d = dim_details.get(key) or {}
        claims.append(
            _claim(
                f"「{d.get('label', key)}」维度表现{business_level(float(score) or 0)}。",
                metric=f"dim_{key}",
                number=round(float(score), 2),
                unit="分",
                table="assessment",
                field=f"dim_{key}",
                query_id=f"Q_enterprise_dim_{key}",
                evidence=[f"weight={d.get('weight')}"],
            )
        )

    bench = await assessment.peer_benchmark(db, enterprise_id)
    if bench:
        for gkey in ("industry", "province", "scale"):
            g = (bench.get("groups") or {}).get(gkey)
            if not g:
                continue
            _dev = g.get("deviation") or 0
            _dev_trend = "高于" if _dev > 0 else "低于" if _dev < 0 else "接近"
            claims.append(
                _claim(
                    f"在「{g['value']}」同群主体中，{name}综合经营表现排名第 {g['rank']}/{g['peer_total']}，"
                    f"{_dev_trend}同群平均水平。",
                    metric=f"peer_{gkey}_percentile",
                    number=g["percentile"],
                    unit="",
                    table="core_metrics",
                    field="overall_score",
                    query_id=f"Q_enterprise_peer_{gkey}",
                    confidence="inferred",
                    evidence=[f"rank={g['rank']}/{g['peer_total']}", f"mean={g['group_mean']}"],
                )
            )

    # 风险成因（负向项）
    attr = profile.get("attribution") or {}
    neg_items: list[tuple[str, dict[str, Any]]] = []
    for key, d in (attr.get("dimensions") or {}).items():
        for n in d.get("negative") or []:
            neg_items.append((d.get("label", key), n))
    for dim_label, n in neg_items[:5]:
        claims.append(
            _claim(
                f"风险成因 · {dim_label}：{n['item']}。",
                metric="risk_factor",
                number=n.get("deduction"),
                unit="分",
                table="assessment",
                field="attribution",
                query_id="Q_enterprise_neg",
                evidence=[f"dimension={dim_label}", f"item={n['item']}"],
            )
        )

    # 预警信号
    signals = profile.get("warning_signals") or []
    if signals:
        signal_labels = [WARNING_SIGNAL_LABELS.get(s, s) for s in signals]
        claims.append(
            _claim(
                f"预警信号：{'、'.join(signal_labels)}。",
                metric="warning_signal_count",
                number=len(signals),
                unit="项",
                table="core_metrics",
                field="warning_signals",
                query_id="Q_enterprise_signals",
                confidence="inferred",
                evidence=[f"signals={signals}"],
            )
        )

    if attr.get("summary"):
        claims.append(
            _claim(
                attr["summary"],
                metric="overall_score",
                number=profile["overall_score"],
                unit="分",
                table="assessment",
                field="overall_score",
                query_id="Q_enterprise_attribution",
                evidence=[f"dimensions={len(attr.get('dimensions') or {})}"],
            )
        )

    radar = enterprise_radar_chart(profile)
    meta: dict[str, Any] = {
        "enterprise_id": enterprise_id,
        "enterprise_label": name,
        "enterprise_name": name,
        "industry_l1": profile.get("industry_l1"),
        "province": profile.get("province"),
        "overall_score": profile["overall_score"],
        "risk_level": profile["risk_level"],
        "warning_signals": signals,
        "charts": radar,
    }
    return claims, meta


def derive_enterprise_followups(meta: dict[str, Any], claims: list[Claim]) -> list[str]:
    """个体下钻追问：默认三项（含个体深度报告入口）。"""
    return list(ENTERPRISE_FOLLOWUPS)


async def build_report_ready_claims(
    session_id: str, dimension: str
) -> tuple[list[Claim], dict]:
    from app.services import conclusion_store

    covered = await run_blocking(conclusion_store.covered_functions, session_id, None)
    needed = {"trend", "authenticity", "fraud", "score", "benchmark", "signal"}
    have = covered & needed
    missing = sorted(needed - have)
    claims = [
        _claim(
            f"当前会话已覆盖功能：{('、'.join(sorted(have)) if have else '无')}；"
            f"建议补全：{('、'.join(missing) if missing else '已基本齐全，可生成组合报告')}。",
            metric="coverage_count",
            number=len(have),
            unit="项",
            table="conclusion_store",
            field="function",
            query_id="Q_report_coverage",
            confidence="inferred",
            evidence=[f"covered={sorted(have)}", f"missing={missing}"],
        )
    ]
    return claims, {"covered": sorted(have), "missing": missing}


DEFAULT_FOLLOWUPS = {
    "trend": ["进一步看真实性交叉验证", "按地区拆分趋势", "哪些行业舞弊信号更多"],
    "authenticity": ["结合舞弊发票信号看", "看行业对标基准", "生成真实性专题报告"],
    "fraud": ["对比各行业趋势", "看营收偏差真实性", "按地区筛预警信号"],
    "score": ["分析各行业趋势走向", "查看风险预警信号", "做行业对标"],
    "benchmark": ["分析趋势走向", "看收入真实性表现", "出组合报告"],
    "signal": ["分析舞弊切片", "看行业趋势", "生成风险报告"],
    "financial": ["看偿债与营运能力拆解", "生成财务健康体检报告", "对照行业财务基准"],
    "tax": ["看欠税与违法信号分布", "生成税务合规体检报告", "对照税负水平"],
    "report": ["补充真实性分析", "补充舞弊检测", "按行业看趋势"],
    "email_report": ["先生成报告再发送", "查看覆盖度", "分析行业趋势"],
    "general": ["分析各行业的趋势走向", "按地区对比信用评分", "查看有哪些风险预警"],
}


def _derive_followups(fn: str, meta: dict[str, Any], claims: list[Claim]) -> list[str]:
    """由当前切片 meta 生成 1 条数据驱动追问，再补默认项。"""
    dynamic: list[str] = []
    if fn == "trend":
        inds = meta.get("industries") or []
        if len(inds) >= 2:
            dynamic.append(
                f"为什么{zh_industry(inds[0]['industry_l1'])}同比高于{zh_industry(inds[-1]['industry_l1'])}？"
            )
    elif fn == "score":
        by_ind = meta.get("by_industry") or []
        if by_ind:
            dynamic.append(f"深入分析{zh_industry(by_ind[0]['industry_l1'])}行业信用分构成")
    elif fn == "fraud":
        sc = meta.get("signal_counts") or {}
        if sc:
            top = max(sc.items(), key=lambda x: x[1])[0]
            dynamic.append(f"为什么「{zh_signal(top)}」舞弊信号最突出？")
    elif fn == "signal":
        if meta.get("low_credit"):
            dynamic.append("低信用等级集中在哪些行业？")
    elif fn == "authenticity" and meta.get("suspicious_count"):
        dynamic.append(f"交叉偏差可疑 {meta['suspicious_count']} 家的共性是什么？")

    defaults = list(DEFAULT_FOLLOWUPS.get(fn, DEFAULT_FOLLOWUPS["general"]))
    if fn == "general" and meta.get("guidance"):
        defaults = list(meta["guidance"])
    merged = dynamic + [q for q in defaults if q not in dynamic]
    return merged[:3]


async def run_judgment(
    db: AsyncSession, intent: IntentResult, session_id: str
) -> tuple[list[Claim], list[str], dict[str, Any]]:
    fn, dim = intent.function, intent.dimension
    industry = intent.industry_l1
    province = intent.province
    charts = None
    meta: dict[str, Any] = {"function": fn, "dimension": dim}
    if province:
        meta["province"] = province

    if fn == "trend":
        claims, meta2 = await build_trend_industry_claims(db, industry, province=province, enterprise_ids=intent.enterprises)
    elif fn == "score":
        claims, meta2 = await build_score_claims(db, industry, dimension=dim, province=province, enterprise_ids=intent.enterprises)
    elif fn == "benchmark":
        claims, meta2 = await build_benchmark_claims(db, industry, province=province, enterprise_ids=intent.enterprises)
    elif fn == "authenticity":
        claims, meta2 = await build_authenticity_claims(db, industry, province=province, enterprise_ids=intent.enterprises)
    elif fn == "fraud":
        claims, meta2 = await build_fraud_claims(db, industry, province=province, enterprise_ids=intent.enterprises)
    elif fn == "financial":
        claims, meta2 = await build_financial_claims(db, industry, dimension=dim, province=province, enterprise_ids=intent.enterprises)
    elif fn == "tax":
        claims, meta2 = await build_tax_claims(db, industry, dimension=dim, province=province, enterprise_ids=intent.enterprises)
    elif fn == "signal" or (fn == "general" and dim == "signal"):
        claims, meta2 = await build_signal_claims(
            db, industry_l1=industry, province=province, enterprise_ids=intent.enterprises
        )
        fn = "signal"
    elif fn in ("report", "email_report"):
        claims, meta2 = await build_report_ready_claims(session_id, dim)
    else:
        # general：给趋势摘要 + 明确引导（引导用户用具体问法触发风控分析）
        claims, meta2 = await build_trend_industry_claims(db, industry, province=province, enterprise_ids=intent.enterprises)
        guidance = [
            "分析各行业的趋势走向",
            "按地区对比信用评分",
            "识别进销错配与异常开票信号",
            "查看有哪些风险预警",
            "生成报告",
        ]
        claims = claims[:3] + [
            _claim(
                "当前问题未命中具体风控维度。你可以这样问：" + "；".join(guidance) + "。",
                metric="hint",
                number=None,
                unit="",
                table="core_metrics",
                field="industry_l1",
                query_id="Q_general_hint",
                confidence="inferred",
                evidence=["guidance=general"],
            )
        ]
        meta2["guidance"] = guidance

    meta.update(meta2)
    charts = meta2.get("charts")
    if charts:
        meta["charts"] = charts

    synthesis, syn_meta = await run_blocking(
        build_session_synthesis_claims,
        session_id,
        pending_function=fn if fn in ANALYSIS_FUNCTIONS else None,
        pending_claims=without_synthesis_claims(claims) if fn in ANALYSIS_FUNCTIONS else None,
    )
    if synthesis:
        claims = synthesis + claims
        meta.update(syn_meta)

    followups = _derive_followups(fn, meta, claims)
    return claims, followups, meta


# ---------------------------------------------------------------------------
# SemanticQuery 执行层（P0）：8 类查询 + FAQ/方法论。数字全部来自算法，不经 LLM。
# ---------------------------------------------------------------------------

_PERCENT_METRICS = frozenset(
    {"revenue_yoy", "profit_margin", "revenue_deviation", "profit_yoy", "debt_ratio", "tax_on_time_rate",
     "customer_concentration", "supplier_concentration", "category_concentration",
     "vat_burden", "income_tax_burden"}
)


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0.0 or vy == 0.0:
        return 0.0
    return cov / ((vx ** 0.5) * (vy ** 0.5))


def _metric_to_source_field(metric: str) -> str | None:
    """CoreMetrics 列映射（不含 assessment 计算分）。"""
    return {
        "credit_score": "credit_score",
        "avg_credit_score": "credit_score",
        "avg_composite": "fraud_composite_score",
        "revenue_yoy": "revenue_yoy",
        "revenue_deviation": "revenue_deviation",
        "profit_margin": "profit_margin",
        "tax_on_time_rate": "tax_on_time_rate",
        "profit_yoy": "profit_yoy",
        "debt_ratio": "debt_ratio",
        "customer_concentration": "customer_concentration",
        "supplier_concentration": "supplier_concentration",
        "category_concentration": "category_concentration",
        "vat_burden": "vat_burden",
        "income_tax_burden": "income_tax_burden",
        "correction_times": "correction_times",
        "social_headcount": "social_headcount",
        "tax_late_penalty_cnt": "tax_late_penalty_cnt",
        "void_invoice_cnt": "void_invoice_cnt",
        "unit_price_ratio": "unit_price_ratio",
        "change_cnt": "change_cnt",
    }.get(metric)


def _trace_for_metric(metric: str) -> tuple[str, str]:
    """Claim 溯源 (table, field)。综合/维度分来自 assessment，勿误标 credit_score。"""
    if metric in ("overall_score", "avg_score"):
        return "assessment", "overall_score"
    if metric.startswith("dim_"):
        return "assessment", metric
    if metric == "avg_composite":
        return "assessment", "fraud_composite_score"
    sf = _metric_to_source_field(metric)
    return "core_metrics", sf or metric



def _metric_label(metric: str) -> str:
    from app.services.metric_registry import RUNTIME_METRIC_LABELS

    return RUNTIME_METRIC_LABELS.get(metric, metric)


# 评分类指标：报告/语义层展示一律转业务话术，不暴露原始得分（稳健/中等/偏弱）。
_SCORE_METRICS: set[str] = {
    "overall_score",
    "credit_score",
    "authenticity_score",
    "fraud_composite_score",
    "avg_score",
    "avg_credit_score",
    "avg_authenticity_score",
    "avg_composite",
    "dim_tax_health",
    "dim_authenticity",
    "dim_invoice",
    "dim_industry",
    "dim_legal",
    "dim_finance",
    "risk_factor",
    "peer_industry_percentile",
    "peer_province_percentile",
    "peer_scale_percentile",
}


def _metric_value_text(metric: str, avg: float) -> str:
    """评分类指标 → 业务话术（稳健/中等/偏弱）；业务比率类保留数值（均值 XX）。"""
    if metric in _SCORE_METRICS:
        return business_level(float(avg))
    return f"均值 {float(avg):.1f}"


def _sq_industry(sq: SemanticQuery) -> str | None:
    return (sq.filters.get("industry_l1") or [None])[0]


def _sq_province(sq: SemanticQuery) -> str | None:
    return (sq.filters.get("province") or [None])[0]


def _sq_dimension(sq: SemanticQuery) -> str:
    dims = sq.dimensions or []
    if "province" in dims:
        return "region"
    if "industry_l1" in dims:
        return "industry"
    return "overall"


def _avg_for_rows(rows: list[CoreMetrics], metric: str) -> float | None:
    sf = _metric_to_source_field(metric)
    if not sf:
        return None
    vals = [_f(getattr(m, sf)) for m in rows if getattr(m, sf) is not None]
    if not vals:
        return None
    avg = sum(vals) / len(vals)
    return avg * (100 if metric in _PERCENT_METRICS else 1)


async def _distinct_industries(db: AsyncSession) -> list[str]:
    rows = await _load_metrics(db)
    return sorted({m.industry_l1 for m in rows if m.industry_l1})


async def _metric_dispatcher(
    db: AsyncSession, sq: SemanticQuery, metric: str
) -> tuple[list[Claim], dict[str, Any]]:
    """按 metric 把 aggregation/lookup 委托到既有 builder，或走通用基础指标均值。"""
    industry = _sq_industry(sq)
    province = _sq_province(sq)
    if metric == "overall_score":
        return await build_score_claims(db, industry, dimension="overall", province=province)
    if metric == "credit_score":
        return await build_score_claims(db, industry, dimension=_sq_dimension(sq), province=province)
    if metric == "authenticity_score":
        return await build_authenticity_claims(db, industry, province=province)
    if metric == "fraud_composite_score":
        return await build_fraud_claims(db, industry, province=province)
    if metric == "revenue_yoy":
        return await build_trend_industry_claims(db, industry, province=province)
    return await _generic_simple_avg(db, sq, metric)


async def _generic_simple_avg(
    db: AsyncSession, sq: SemanticQuery, metric: str
) -> tuple[list[Claim], dict[str, Any]]:
    sf = _metric_to_source_field(metric)
    if not sf:
        return await build_score_claims(db, _sq_industry(sq), dimension=_sq_dimension(sq), province=_sq_province(sq))
    rows = await _load_metrics(db, _sq_industry(sq), province=_sq_province(sq))
    label = _metric_label(metric)
    if not rows:
        return (
            [_claim("暂无样本。", metric="sample_count", number=0, unit="家", table="core_metrics", field="enterprise_id", query_id="Q_semantic_empty")],
            {},
        )
    dim = _sq_dimension(sq)
    if dim in ("industry", "region"):
        key = "industry_l1" if dim == "industry" else "province"
        groups: dict[str, list[CoreMetrics]] = {}
        for m in rows:
            groups.setdefault(getattr(m, key) or "其他", []).append(m)
        stats = []
        for g, group in groups.items():
            avg = _avg_for_rows(group, metric)
            if avg is None:
                continue
            stats.append({"group": g, "n": len(group), "avg": round(avg, 2)})
        stats.sort(key=lambda x: -x["avg"])
        claims = [
            _claim(
                f"{s['group']}{label}{_metric_value_text(metric, s['avg'])}（样本 {s['n']}）。",
                metric=metric,
                number=s["avg"],
                unit="",
                table="core_metrics",
                field=sf,
                query_id="Q_semantic_group",
            )
            for s in stats[:8]
        ]
        chart = {
            "type": "bar",
            "data": {
                "labels": [s["group"] for s in stats[:8]],
                "series": [{"name": label, "values": [s["avg"] for s in stats[:8]]}],
            },
        }
        return claims, {"charts": chart}
    avg = _avg_for_rows(rows, metric)
    if avg is None:
        return (
            [
                _claim(
                    f"样本无有效{label}数据，无法计算均值。",
                    metric=metric,
                    number=None,
                    unit="",
                    table="core_metrics",
                    field=sf,
                    query_id="Q_semantic_overall_abstain",
                    confidence="inferred",
                    evidence=[f"sample_count={len(rows)}"],
                )
            ],
            {"sample_count": len(rows)},
        )
    claim = _claim(
        f"样本{label}{_metric_value_text(metric, avg)}（样本 {len(rows)} 家）。",
        metric=metric,
        number=round(avg, 2),
        unit="",
        table="core_metrics",
        field=sf,
        query_id="Q_semantic_overall",
        evidence=[f"n={len(rows)}"],
    )
    return [claim], {}


async def build_lookup_claims(
    db: AsyncSession, sq: SemanticQuery
) -> tuple[list[Claim], dict[str, Any]]:
    metric = (sq.metrics or ["overall_score"])[0]
    return await _metric_dispatcher(db, sq, metric)


async def build_aggregation_claims(
    db: AsyncSession, sq: SemanticQuery
) -> tuple[list[Claim], dict[str, Any]]:
    metric = (sq.metrics or ["overall_score"])[0]
    return await _metric_dispatcher(db, sq, metric)


async def build_comparison_claims(
    db: AsyncSession, sq: SemanticQuery
) -> tuple[list[Claim], dict[str, Any]]:
    metric = (sq.metrics or ["credit_score"])[0]
    label = _metric_label(metric)
    compare = sq.compare[0] if sq.compare else None
    if not compare or not compare.values:
        return await build_score_claims(db, None, dimension="region", province=None)

    dim = compare.dimension
    values = compare.values
    per_value: list[dict[str, Any]] = []
    missing: list[str] = []
    for v in values:
        industry = v if dim == "industry_l1" else _sq_industry(sq)
        province = v if dim == "province" else _sq_province(sq)
        rows = await _load_metrics(db, industry, province=province)
        avg = _avg_for_rows(rows, metric)
        if avg is None:
            missing.append(v)
            continue
        per_value.append({"value": v, "n": len(rows), "avg": round(avg, 2)})

    claims: list[Claim] = []
    # 无样本的值显式说明（不再静默跳过）：小样本/跨省时避免用户误以为只比了部分对象。
    trace_table, trace_field = _trace_for_metric(metric)
    for m in missing:
        claims.append(
            _claim(
                f"{m}暂无样本数据，无法参与对比。",
                metric="compare_no_sample",
                number=None,
                unit="",
                table=trace_table,
                field=trace_field,
                query_id="Q_comparison_no_sample",
                confidence="inferred",
            )
        )

    if not per_value:
        if not claims:
            return await build_score_claims(db, None, dimension="region", province=None)
        return claims, {"comparison": [], "charts": None}

    for p in per_value:
        claims.append(
            _claim(
                f"{p['value']}{label}{_metric_value_text(metric, p['avg'])}（样本 {p['n']}）。",
                metric=f"compare_{metric}",
                number=p["avg"],
                unit="",
                table=trace_table,
                field=trace_field,
                query_id="Q_comparison_value",
            )
        )
    if len(per_value) >= 2:
        top = max(per_value, key=lambda x: x["avg"])
        bottom = min(per_value, key=lambda x: x["avg"])
        claims.append(
            _claim(
                f"对比：{top['value']}{label}{_metric_value_text(metric, top['avg'])}，"
                f"{bottom['value']}{label}{_metric_value_text(metric, bottom['avg'])}。",
                metric="compare_spread",
                number=round(top["avg"] - bottom["avg"], 2) if metric not in _SCORE_METRICS else None,
                unit="",
                table=trace_table,
                field=trace_field,
                query_id="Q_comparison_spread",
                confidence="inferred",
                evidence=[f"top={top['value']}", f"bottom={bottom['value']}"],
            )
        )

    chart = {
        "type": "bar",
        "data": {
            "labels": [p["value"] for p in per_value],
            "series": [{"name": label, "values": [p["avg"] for p in per_value]}],
        },
    }
    return claims, {"comparison": per_value, "charts": chart}


async def build_ranking_claims(
    db: AsyncSession, sq: SemanticQuery
) -> tuple[list[Claim], dict[str, Any]]:
    metric = (sq.metrics or ["credit_score"])[0]
    label = _metric_label(metric)
    limit = sq.limit or 10
    order = (sq.sort.order if sq.sort else "desc")
    ordinal = "名" if order == "desc" else "低"
    dims = sq.dimensions or []

    if "industry_l1" in dims or "province" in dims:
        key = "industry_l1" if "industry_l1" in dims else "province"
        # 综合分来自 assessment，禁止用 credit_score 顶替
        if metric in ("overall_score", "avg_score"):
            from app.services import assessment

            items = await assessment.list_all(db)
            industry_f = _sq_industry(sq)
            province_f = _sq_province(sq)
            groups_scores: dict[str, list[float]] = {}
            for it in items:
                if industry_f and (it.get("industry_l1") or "") != industry_f:
                    continue
                if province_f and (it.get("province") or "") != province_f:
                    continue
                g = it.get(key) or "其他"
                score = it.get("overall_score")
                if score is None:
                    continue
                groups_scores.setdefault(g, []).append(float(score))
            stats = [
                {"group": g, "avg": round(sum(vs) / len(vs), 2), "n": len(vs)}
                for g, vs in groups_scores.items()
                if vs
            ]
            stats.sort(key=lambda x: x["avg"], reverse=(order == "desc"))
            stats = stats[:limit]
            if not stats:
                return (
                    [
                        _claim(
                            "当前范围内有效经营样本不足，暂无法排名。",
                            metric="sample_count",
                            number=0,
                            unit="家",
                            table="assessment",
                            field="overall_score",
                            query_id="Q_ranking_empty",
                        )
                    ],
                    {"ranking": []},
                )
            claims = [
                _claim(
                    f"第{i + 1}{ordinal}：{s['group']}，综合经营表现{business_level(float(s['avg']))}（样本 {s['n']} 家）。",
                    metric=f"rank_{metric}",
                    number=s["avg"],
                    unit="分",
                    table="assessment",
                    field="overall_score",
                    query_id="Q_ranking_group",
                    confidence="inferred",
                )
                for i, s in enumerate(stats)
            ]
            chart = {
                "type": "bar",
                "data": {
                    "labels": [s["group"] for s in stats],
                    "series": [{"name": label, "values": [s["avg"] for s in stats]}],
                },
            }
            return claims, {"ranking": stats, "charts": chart}

        rows = await _load_metrics(db, _sq_industry(sq), province=_sq_province(sq))
        sf = _metric_to_source_field(metric)
        if not sf:
            return (
                [
                    _claim(
                        f"指标 {label} 无法按 {key} 聚合排名。",
                        metric="rank_unsupported",
                        number=None,
                        unit="",
                        table="core_metrics",
                        field=metric,
                        query_id="Q_ranking_unsupported",
                    )
                ],
                {},
            )
        groups: dict[str, list[CoreMetrics]] = {}
        for m in rows:
            groups.setdefault(getattr(m, key) or "其他", []).append(m)
        stats = []
        for g, group in groups.items():
            avg = _avg_for_rows(group, metric)
            if avg is None:
                continue
            stats.append({"group": g, "avg": round(avg, 2), "n": len(group)})
        stats.sort(key=lambda x: x["avg"], reverse=(order == "desc"))
        stats = stats[:limit]
        claims = [
            _claim(
                f"第{i + 1}{ordinal}：{s['group']}，{label}{_metric_value_text(metric, s['avg'])}（样本 {s['n']}）。",
                metric=f"rank_{metric}",
                number=s["avg"],
                unit="",
                table=_trace_for_metric(metric)[0],
                field=_trace_for_metric(metric)[1],
                query_id="Q_ranking_group",
                confidence="inferred",
            )
            for i, s in enumerate(stats)
        ]
        chart = {
            "type": "bar",
            "data": {
                "labels": [s["group"] for s in stats],
                "series": [{"name": label, "values": [s["avg"] for s in stats]}],
            },
        }
        return claims, {"ranking": stats, "charts": chart}

    # 企业排名：仅匿名标签（脱敏，绝无实名）
    from app.services import assessment

    items = await assessment.list_all(db)
    items = sorted(items, key=lambda x: float(x.get("overall_score") or 0), reverse=(order == "desc"))
    items = items[:limit]
    claims = [
        _claim(
            f"第{i + 1}{ordinal}：{it.get('display_name') or it.get('enterprise_name') or it.get('display_label') or '—'}，"
            f"综合经营表现{business_level(float(it.get('overall_score') or 0))}。",
            metric="rank_overall_score",
            number=round(float(it.get("overall_score") or 0), 2),
            unit="分",
            table="assessment",
            field="overall_score",
            query_id="Q_ranking_enterprise",
            confidence="inferred",
            evidence=[f"risk_level={it.get('risk_level')}"],
        )
        for i, it in enumerate(items)
    ]
    chart = {
        "type": "bar",
        "data": {
            "labels": [it.get("display_name") or it.get("enterprise_name") or it.get("display_label") or "—" for it in items],
            "series": [{"name": "综合经营表现", "values": [float(it.get("overall_score") or 0) for it in items]}],
        },
    }
    return claims, {"ranking": items, "charts": chart}


async def build_distribution_claims(
    db: AsyncSession, sq: SemanticQuery
) -> tuple[list[Claim], dict[str, Any]]:
    metric = (sq.metrics or ["risk_level"])[0]
    if metric == "signal_total":
        return await build_signal_claims(
            db, industry_l1=_sq_industry(sq), province=_sq_province(sq)
        )

    from app.services import assessment

    summary = await assessment.get_dashboard_summary(db)
    dist = summary.get("risk_distribution") or {}
    if not dist:
        return (
            [_claim("暂无风险等级分布数据。", metric="sample_count", number=0, unit="家", table="core_metrics", field="risk_level", query_id="Q_distribution_empty")],
            {},
        )
    total = summary.get("sample_count") or 0
    claims = [
        _claim(
            f"风险等级「{level}」主体 {cnt} 家。",
            metric="risk_level_count",
            number=cnt,
            unit="家",
            table="core_metrics",
            field="risk_level",
            query_id="Q_distribution_level",
            confidence="inferred",
            evidence=[f"total={total}"],
        )
        for level, cnt in dist.items()
    ]
    chart = {
        "type": "pie",
        "data": {
            "labels": list(dist.keys()),
            "series": [{"name": "主体数", "values": [dist[k] for k in dist]}],
        },
    }
    return claims, {"risk_distribution": dist, "charts": chart}


async def build_segmentation_claims(
    db: AsyncSession, sq: SemanticQuery
) -> tuple[list[Claim], dict[str, Any]]:
    metric = (sq.metrics or ["credit_score"])[0]
    dim = _sq_dimension(sq)
    if dim == "overall":
        dim = "industry"  # segmentation 未指定维度时默认按行业拆分（保持旧行为）
    industry = _sq_industry(sq)
    province = _sq_province(sq)
    if metric in ("credit_score", "overall_score"):
        return await build_score_claims(db, industry, dimension=dim, province=province)
    if metric == "revenue_yoy":
        return await build_trend_industry_claims(db, industry, province=province)

    inds = await _distinct_industries(db)
    stats: list[dict[str, Any]] = []
    claims: list[Claim] = []

    if metric == "authenticity_score":
        from app.services import authenticity_engine

        for ind in inds:
            rows = await _load_metrics(db, ind)
            if not rows:
                continue
            r = await run_blocking(
                authenticity_engine.analyze_authenticity_batch, rows[:120], industry_l1=ind
            )
            avg = r.get("avg_authenticity_score")
            n = r.get("sample_count") or 0
            stats.append({"group": ind, "avg": avg, "n": n})
            claims.append(
                _claim(
                    f"{zh_industry(ind) or ind}行业收入真实性整体{business_level(float(avg or 0))}（样本 {n} 家），"
                    f"建议对申报、开票、财报口径不一致的企业进一步核查收入真实性。",
                    metric="seg_authenticity_score",
                    number=avg,
                    unit="分",
                    table="core_metrics",
                    field="revenue_deviation",
                    query_id="Q_seg_authenticity",
                    evidence=[f"industry={ind}"],
                )
            )
    elif metric == "fraud_composite_score":
        from app.services import fraud_engine

        for ind in inds:
            rows = await _load_metrics(db, ind)
            if not rows:
                continue
            tuples = [(m.enterprise_id, m.display_label, m.industry_l1, m.display_name) for m in rows[:40]]
            try:
                out = await run_blocking(fraud_engine.analyze_metrics_batch, tuples, max_n=40)
            except Exception:
                continue
            if out.get("sample_count", 0) == 0:
                continue
            avg = out.get("avg_composite")
            n = out.get("sample_count") or 0
            flagged = out.get("flagged_count") or 0
            stats.append({"group": ind, "avg": avg, "n": n})
            claims.append(
                _claim(
                    f"{zh_industry(ind) or ind}行业 {n} 家主体中，{flagged} 家存在进销错配、红字发票异常等"
                    f"发票舞弊迹象，建议核查票据交易背景与货物凭证。",
                    metric="seg_fraud_composite",
                    number=flagged,
                    unit="家",
                    table="syx_invoice_details",
                    field="scbm",
                    query_id="Q_seg_fraud",
                    evidence=[f"industry={ind}"],
                )
            )
    else:
        return await build_score_claims(db, None, dimension="industry", province=_sq_province(sq))

    stats.sort(key=lambda x: -(float(x.get("avg") or 0)))
    if stats:
        chart = {
            "type": "bar",
            "data": {
                "labels": [s["group"] for s in stats],
                "series": [{"name": _metric_label(metric), "values": [s["avg"] for s in stats]}],
            },
        }
        return claims, {"segmentation": stats, "charts": chart}
    return claims, {"segmentation": stats}


async def build_correlation_claims(
    db: AsyncSession, sq: SemanticQuery
) -> tuple[list[Claim], dict[str, Any]]:
    metrics = sq.metrics or ["credit_score", "revenue_yoy"]
    a, b = metrics[0], metrics[1]
    sfa = _metric_to_source_field(a)
    sfb = _metric_to_source_field(b)
    if not sfa or not sfb:
        return (
            [
                _claim(
                    "相关分析仅支持可溯源的基础指标（如信用分、营收同比、利润率、营收偏差）。",
                    metric="corr_unsupported",
                    number=None,
                    unit="",
                    table="core_metrics",
                    field="enterprise_id",
                    query_id="Q_corr_unsupported",
                    confidence="inferred",
                )
            ],
            {},
        )
    rows = await _load_metrics(db, _sq_industry(sq), province=_sq_province(sq))
    xs: list[float] = []
    ys: list[float] = []
    for m in rows:
        x = getattr(m, sfa, None)
        y = getattr(m, sfb, None)
        if x is None or y is None:
            continue
        xs.append(_f(x))
        ys.append(_f(y))
    if len(xs) < 2:
        return (
            [_claim("样本不足，无法计算相关性。", metric="sample_count", number=len(xs), unit="家", table="core_metrics", field="enterprise_id", query_id="Q_corr_empty", confidence="inferred")],
            {"sample_count": len(xs)},
        )
    r = _pearson(xs, ys)
    la, lb = _metric_label(a), _metric_label(b)
    claims = [
        _claim(
            f"{la}与{lb}的皮尔逊相关系数 {r:.3f}。",
            metric=f"corr_{a}_{b}",
            number=round(r, 4),
            unit="",
            table="core_metrics",
            field=sfa,
            query_id="Q_corr",
            confidence="inferred",
            evidence=[f"n={len(xs)}", f"x={sfa}", f"y={sfb}"],
        )
    ]
    from app.services.chart_payloads import correlation_scatter_chart

    chart = correlation_scatter_chart(xs, ys, x_label=la, y_label=lb)
    return claims, {"correlation": round(r, 4), "n": len(xs), "charts": chart}


SEMANTIC_FOLLOWUPS: dict[str, list[str]] = {
    "lookup": ["按行业拆分看", "生成报告", "查看风险预警"],
    "aggregation": ["分析各行业趋势走向", "查看风险预警", "生成报告"],
    "comparison": ["对比这两个群体的真实性", "看经营表现排名", "生成报告"],
    "trend": ["进一步看真实性交叉验证", "按地区拆分趋势", "生成报告"],
    "ranking": ["深入分析第一名群体", "看排名背后的风险信号", "生成报告"],
    "distribution": ["看舞弊信号分布", "按行业拆风险等级", "生成报告"],
    "segmentation": ["看各行业舞弊信号", "做行业对标", "生成报告"],
    "correlation": ["看行业趋势", "查看风险预警", "生成报告"],
    "faq": ["这个系统能做什么", "数据怎么导入", "报告怎么生成"],
    "methodology": ["如何判断收入真实性", "如何识别发票舞弊", "报告怎么生成"],
}


def _derive_semantic_followups(sq: SemanticQuery, meta: dict[str, Any], claims: list[Claim]) -> list[str]:
    qt = sq.query_type.value if hasattr(sq.query_type, "value") else str(sq.query_type)
    defaults = list(SEMANTIC_FOLLOWUPS.get(qt, DEFAULT_FOLLOWUPS["general"]))
    return defaults[:3]


async def run_semantic_query(
    db: AsyncSession,
    sq: SemanticQuery,
    session_id: str,
    *,
    intent: IntentResult | None = None,
) -> tuple[list[Claim], list[str], dict[str, Any]]:
    """按 query_type 分派到 build_*_claims；复用 run_judgment 的 synthesis + followup 尾巴。"""
    from app.services import faq_kb, semantic_query as sq_lib

    qt = sq.query_type
    if qt == QueryType.trend:
        claims, meta2 = await build_trend_industry_claims(db, _sq_industry(sq), province=_sq_province(sq))
    elif qt == QueryType.lookup:
        claims, meta2 = await build_lookup_claims(db, sq)
    elif qt == QueryType.aggregation:
        claims, meta2 = await build_aggregation_claims(db, sq)
    elif qt == QueryType.comparison:
        claims, meta2 = await build_comparison_claims(db, sq)
    elif qt == QueryType.ranking:
        claims, meta2 = await build_ranking_claims(db, sq)
    elif qt == QueryType.distribution:
        claims, meta2 = await build_distribution_claims(db, sq)
    elif qt == QueryType.segmentation:
        claims, meta2 = await build_segmentation_claims(db, sq)
    elif qt == QueryType.correlation:
        claims, meta2 = await build_correlation_claims(db, sq)
    elif qt == QueryType.faq:
        claims, meta2 = faq_kb.build_faq_claims(sq.raw_query)
    elif qt == QueryType.methodology:
        claims, meta2 = faq_kb.build_methodology_claims(sq.metrics)
    else:
        claims, meta2 = await build_trend_industry_claims(db, _sq_industry(sq), province=_sq_province(sq))

    fn = sq_lib.query_type_to_function(sq)
    dim = sq_lib.query_type_to_dimension(sq)
    meta: dict[str, Any] = {
        "function": fn,
        "dimension": dim,
        "query_type": qt.value,
        "semantic_query": sq_lib.semantic_query_to_dict(sq),
    }
    if _sq_province(sq):
        meta["province"] = _sq_province(sq)
    meta.update(meta2)
    charts = meta2.get("charts")
    if charts:
        meta["charts"] = charts

    synthesis, syn_meta = await run_blocking(
        build_session_synthesis_claims,
        session_id,
        pending_function=fn if fn in ANALYSIS_FUNCTIONS else None,
        pending_claims=without_synthesis_claims(claims) if fn in ANALYSIS_FUNCTIONS else None,
    )
    if synthesis:
        claims = synthesis + claims
        meta.update(syn_meta)

    followups = _derive_semantic_followups(sq, meta, claims)
    return claims, followups, meta
