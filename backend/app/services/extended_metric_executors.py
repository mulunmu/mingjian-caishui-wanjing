"""Deterministic executors for Stage 17 metrics backed by real PostgreSQL fields."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics
from app.models.engine_store import EnterpriseEngineFeatures
from app.models.financials import EnterpriseFinancials
from app.models.profiles import EnterpriseInvoiceProfile
from app.models.core_metrics import LegalEvent
from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.schemas.semantic_query import SemanticQuery
from app.services.authenticity_engine import cross_source_deviation
from app.services.stage17_metric_catalog import (
    CROSS_DEVIATION_METRICS,
    SUPPORTED_EXTENDED_METRICS,
    SUPPORTED_METRIC_KEYS,
)


def _f(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def invoice_ratio(numerator: Any, denominator: Any) -> float | None:
    n = _f(numerator)
    d = _f(denominator)
    if n is None or d is None or d <= 0:
        return None
    return round(n / d * 100, 4)


def ocf_to_revenue(operating_cf: Any, revenue: Any) -> float | None:
    return invoice_ratio(operating_cf, revenue)


def effective_tax_rate(income_tax: Any, total_profit: Any) -> float | None:
    tax = _f(income_tax)
    profit = _f(total_profit)
    if tax is None or profit is None or profit <= 0:
        return None
    return round(tax / profit * 100, 4)


def top5_share(raw_json: str | None, fallback: Any) -> float | None:
    try:
        items = json.loads(raw_json) if raw_json else []
        values = [_f(item.get("share")) for item in items if isinstance(item, dict)]
        values = [value for value in values if value is not None]
        if values:
            return round(sum(values) * 100, 4)
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    fallback_value = _f(fallback)
    return round(fallback_value * 100, 4) if fallback_value is not None else None


def recency_days(event_dates: list[date], today: date | None = None) -> int | None:
    dates = [value for value in event_dates if value is not None]
    if not dates:
        return None
    anchor = today or date.today()
    return max(0, (anchor - max(dates)).days)


def _claim(
    text: str,
    *,
    metric: str,
    value: Any,
    unit: str,
    table: str,
    field: str,
    query_id: str,
    evidence: list[str] | None = None,
    confidence: str = "computed",
) -> Claim:
    numeric = _f(value)
    return Claim(
        claim=text,
        value=ClaimValue(metric=metric, number=numeric, unit=unit) if numeric is not None else None,
        trace=ClaimTrace(table=table, field=field, query_id=query_id),
        confidence=confidence,  # type: ignore[arg-type]
        evidence_chain=evidence or [],
    )


async def _profile_map(db: AsyncSession, ids: list[str]) -> dict[str, EnterpriseInvoiceProfile]:
    if not ids:
        return {}
    result = await db.execute(
        select(EnterpriseInvoiceProfile).where(EnterpriseInvoiceProfile.enterprise_id.in_(ids))
    )
    return {row.enterprise_id: row for row in result.scalars().all()}


async def _financial_map(db: AsyncSession, ids: list[str]) -> dict[str, EnterpriseFinancials]:
    if not ids:
        return {}
    result = await db.execute(
        select(EnterpriseFinancials).where(EnterpriseFinancials.enterprise_id.in_(ids))
    )
    return {row.enterprise_id: row for row in result.scalars().all()}


async def _legal_recency_map(db: AsyncSession, ids: list[str]) -> dict[str, int | None]:
    if not ids:
        return {}
    result = await db.execute(
        select(LegalEvent.enterprise_id, func.max(LegalEvent.event_date))
        .where(LegalEvent.enterprise_id.in_(ids))
        .group_by(LegalEvent.enterprise_id)
    )
    today = date.today()
    out: dict[str, int | None] = {}
    for enterprise_id, latest in result.all():
        if latest is None:
            continue
        event_date = latest.date() if hasattr(latest, "date") else latest
        out[str(enterprise_id)] = recency_days([event_date], today)
    return out


def _value_for_profile(metric: str, profile: EnterpriseInvoiceProfile) -> float | None:
    if metric == "customer_count":
        return _f(profile.customer_count)
    if metric == "customer_hhi":
        return _f(profile.customer_hhi)
    if metric == "customer_top5_concentration":
        return top5_share(profile.top_customers_json, profile.top_customer_share)
    if metric == "supplier_count":
        return _f(profile.supplier_count)
    if metric == "supplier_hhi":
        return _f(profile.supplier_hhi)
    if metric == "supplier_top5_concentration":
        return top5_share(profile.top_suppliers_json, profile.top_supplier_share)
    total_invoices = _f(profile.sales_invoice_cnt) + _f(profile.purchase_invoice_cnt)
    if metric == "invalid_invoice_ratio":
        return invoice_ratio(profile.abnormal_invoice_cnt, total_invoices)
    if metric == "red_invoice_count_ratio":
        return invoice_ratio(profile.red_invoice_cnt, profile.sales_invoice_cnt)
    if metric == "void_invoice_ratio":
        return invoice_ratio(profile.void_invoice_cnt, total_invoices)
    return None


def _value_for_financial(metric: str, financial: EnterpriseFinancials) -> float | None:
    if metric == "ocf_to_revenue":
        return ocf_to_revenue(financial.operating_cf, financial.revenue)
    if metric == "income_tax_effective_rate":
        return effective_tax_rate(financial.income_tax, financial.total_profit)
    return None


def _cross_value(metric: str, row: CoreMetrics) -> float | None:
    cross = cross_source_deviation(
        vat_revenue=_f(row.vat_revenue),
        invoice_revenue=_f(row.invoice_revenue),
        finance_revenue=_f(row.finance_revenue),
        social_months=row.social_months,
    )
    key = "avg_deviation" if metric == "cross_avg_deviation" else "max_deviation"
    return _f(cross.get(key))


def _format_value(value: float, unit: str) -> str:
    if unit == "元" and abs(value) >= 10000:
        return f"{value / 10000:.2f}万元"
    return f"{value:.2f}{unit}"


async def build_extended_metric_claims(
    db: AsyncSession,
    sq: SemanticQuery,
    metric: str,
    core_rows: list[CoreMetrics],
) -> tuple[list[Claim], dict[str, Any]] | None:
    if metric not in SUPPORTED_METRIC_KEYS:
        return None

    entity_filter = set(sq.entities or [])
    rows = [row for row in core_rows if not entity_filter or row.enterprise_id in entity_filter]
    if not rows:
        return ([
            _claim(
                f"样本暂无{metric}数据。",
                metric=metric,
                value=None,
                unit="",
                table="core_metrics",
                field=metric,
                query_id=f"Q_{metric}_empty",
                confidence="inferred",
            )
        ], {"sample_count": 0})

    ids = [row.enterprise_id for row in rows]
    values: dict[str, float | None] = {}
    source_table = "core_metrics"
    source_field = metric
    spec = SUPPORTED_EXTENDED_METRICS.get(metric) or CROSS_DEVIATION_METRICS.get(metric)
    if spec:
        source_table = spec.source_tables[0]
        source_field = spec.source_fields[0]

    if metric in CROSS_DEVIATION_METRICS:
        values = {row.enterprise_id: _cross_value(metric, row) for row in rows}
    elif metric in {
        "customer_count", "customer_hhi", "customer_top5_concentration",
        "supplier_count", "supplier_hhi", "supplier_top5_concentration",
        "invalid_invoice_ratio",
        "red_invoice_count_ratio", "void_invoice_ratio",
    }:
        profiles = await _profile_map(db, ids)
        values = {row.enterprise_id: _value_for_profile(metric, profiles[row.enterprise_id]) if row.enterprise_id in profiles else None for row in rows}
    elif metric in {"ocf_to_revenue", "income_tax_effective_rate"}:
        financials = await _financial_map(db, ids)
        values = {row.enterprise_id: _value_for_financial(metric, financials[row.enterprise_id]) if row.enterprise_id in financials else None for row in rows}
    elif metric == "violation_recency_days":
        values = await _legal_recency_map(db, ids)

    present = [(enterprise_id, value) for enterprise_id, value in values.items() if value is not None]
    if not present:
        return ([
            _claim(
                f"样本暂无有效{spec.name if spec else metric}数据，无法计算。",
                metric=metric,
                value=None,
                unit="",
                table=source_table,
                field=source_field,
                query_id=f"Q_{metric}_abstain",
                evidence=[f"sample_count={len(rows)}"],
                confidence="inferred",
            )
        ], {"sample_count": len(rows), "abstain": True})

    average = sum(value for _, value in present) / len(present)
    unit = spec.unit if spec else ""
    label = spec.name if spec else metric
    if len(present) == 1:
        enterprise_id, value = present[0]
        display = next((row.display_name or row.display_label for row in rows if row.enterprise_id == enterprise_id), enterprise_id)
        text = f"{display}的{label}为 {_format_value(value, unit)}。"
    else:
        text = f"样本{len(present)}家{label}均值为 {_format_value(average, unit)}。"
    return ([
        _claim(
            text,
            metric=metric,
            value=average,
            unit=unit,
            table=source_table,
            field=source_field,
            query_id=f"Q_{metric}_extended",
            evidence=[f"n={len(present)}", f"coverage={len(present)}/{len(rows)}"],
        )
    ], {"sample_count": len(rows), "valid_count": len(present), "source_table": source_table, "source_field": source_field})
