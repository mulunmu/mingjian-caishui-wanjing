"""Executors connecting validated semantic metric tools to the deterministic engine."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.claim import claims_to_dict
from app.schemas.semantic_query import QueryType, SemanticQuery
from app.services.stage17_metric_catalog import SUPPORTED_METRIC_KEYS as STAGE17_METRIC_KEYS


SUPPORTED_METRIC_KEYS: set[str] = {
    "overall_score",
    "credit_score",
    "authenticity_score",
    "fraud_composite_score",
    "industry_score",
    "revenue_yoy",
    "revenue_deviation",
    "profit_margin",
    "tax_on_time_rate",
    "profit_yoy",
    "debt_ratio",
    "customer_concentration",
    "supplier_concentration",
    "category_concentration",
    "vat_burden",
    "income_tax_burden",
    "correction_times",
    "social_headcount",
    "tax_late_penalty_cnt",
    "void_invoice_cnt",
    "unit_price_ratio",
    "change_cnt",
    "tax_arrears_cnt",
    "tax_violation_cnt",
    "high_severity_cnt",
    "invoice_cnt",
    "invoice_monthly_avg",
    "red_invoice_cnt",
    "vat_revenue",
    "invoice_revenue",
    "finance_revenue",
    "loan_cnt",
    "loan_amount",
    "cash_flow_net",
    "current_ratio",
    "quick_ratio",
    "gross_margin",
    "net_margin",
    "roe",
    "roa",
    "receivables_turnover",
    "inventory_turnover",
    "asset_turnover",
    "social_months",
    "cash_flow_level",
    "credit_level",
    "finance_score",
    "invoice_score",
    "is_dishonesty",
    "is_execution",
    "legal_score",
    "social_trend",
    "tax_health_score",
    "suspicious_count",
    "flagged_count",
    "peer_industry_percentile",
    "peer_province_percentile",
    "signal_total",
    "tax_violation",
    "high_dev",
    "low_credit",
}
SUPPORTED_METRIC_KEYS.update(STAGE17_METRIC_KEYS)

ANALYSIS_OPERATOR_TOOL_IDS = {
    "operator_compare_industry",
    "operator_compare_province",
    "operator_change_rate",
    "operator_proportion",
    "operator_summary",
    "operator_rank",
    "operator_trend",
    "operator_root_cause",
}


def semantic_executor_tool_ids() -> set[str]:
    return {f"metric_{metric}" for metric in SUPPORTED_METRIC_KEYS}.union(
        ANALYSIS_OPERATOR_TOOL_IDS
    )


def _param_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _build_semantic_query(metric_key: str, params: dict[str, Any]) -> SemanticQuery:
    filters: dict[str, list[str]] = {}
    for key in ("industry_l1", "industry_l2", "province", "city", "scale_label"):
        values = _param_list(params.get(key))
        if values:
            filters[key] = values
    entities = _param_list(params.get("entities"))
    entity = params.get("entity")
    if entity and str(entity) not in entities:
        entities.append(str(entity))
    return SemanticQuery(
        query_type=QueryType.lookup,
        metrics=[metric_key],
        dimensions=[str(params["dimension"])] if params.get("dimension") else [],
        filters=filters,
        entities=entities,
        raw_query=str(params.get("query") or ""),
        confidence=float(params.get("confidence") or 1.0),
        source="corrected",
    )


def build_semantic_tool_executors(
    *,
    db: AsyncSession,
    session_id: str,
) -> dict[str, Callable[..., Any]]:
    from app.services import judgment_service

    executors: dict[str, Callable[..., Any]] = {}
    for metric_key in SUPPORTED_METRIC_KEYS:
        tool_id = f"metric_{metric_key}"

        async def execute(
            *,
            params: dict[str, Any],
            dependency_results: dict[str, Any],
            _metric_key: str = metric_key,
        ) -> dict[str, Any]:
            _ = dependency_results
            sq = _build_semantic_query(_metric_key, params)
            claims, followups, meta = await judgment_service.run_semantic_query(
                db,
                sq,
                session_id,
            )
            return {
                "claims": claims_to_dict(claims),
                "followups": followups,
                "meta": meta,
            }

        executors[tool_id] = execute
    from app.services.analysis_operator_executors import (
        build_analysis_operator_executors,
    )

    executors.update(
        build_analysis_operator_executors(db=db, session_id=session_id)
    )
    return executors
