"""Idempotent seed for Metric Catalog v2, thresholds, tools, and aliases."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.models.core_metrics import CoreMetrics
from app.models.metric_registry import MetricDefinition
from app.models.semantic_registry import (
    ThresholdRule,
    ToolAlias,
    ToolDefinition,
    ToolDependency,
    ToolExample,
)
from app.services.metric_catalog_v2 import P0_CANDIDATES
from app.services.metric_registry import (
    CANONICAL_METRICS,
    CROSS_AVG_DEVIATION_WARN,
    CROSS_MAX_DEVIATION_WARN,
    REVENUE_DEVIATION_WARN,
    THRESHOLD_REQUIRED_METRICS,
)
from app.services.financial_benchmarks import FINANCIAL_RATIOS
from app.services.report_templates import CHAPTER_REGISTRY


SCENARIO_DEPENDENCIES: dict[str, list[str]] = {
    "scenario_loan_readiness": [
        "metric_debt_ratio",
        "metric_cash_flow_level",
        "metric_tax_arrears_cnt",
    ],
    "scenario_business_stability": [
        "metric_change_cnt",
        "metric_social_headcount",
        "metric_revenue_yoy",
    ],
    "scenario_shell_company_risk": [
        "metric_social_headcount",
        "metric_invoice_cnt",
        "metric_change_cnt",
    ],
    "scenario_invoice_anomaly": [
        "metric_red_invoice_cnt",
        "metric_void_invoice_cnt",
        "metric_customer_concentration",
    ],
    "scenario_tax_compliance": [
        "metric_vat_burden",
        "metric_tax_arrears_cnt",
        "metric_tax_violation_cnt",
    ],
    "scenario_growth_quality": [
        "metric_revenue_yoy",
        "metric_profit_yoy",
        "metric_cash_flow_level",
    ],
    "scenario_operating_deterioration": [
        "metric_revenue_yoy",
        "metric_profit_yoy",
        "metric_cash_flow_level",
    ],
}

MULTILINGUAL_ALIASES: dict[str, list[str]] = {
    "debt_ratio": ["debt ratio", "leverage ratio", "liability ratio"],
    "cash_flow_level": ["cash flow", "cash flow health", "cash flow status"],
    "revenue_yoy": ["revenue growth", "year over year revenue"],
    "profit_margin": ["profit margin", "profitability"],
    "vat_burden": ["VAT burden", "value added tax burden"],
    "income_tax_burden": ["income tax burden", "effective income tax rate"],
    "tax_on_time_rate": ["tax payment on time", "tax punctuality"],
    "tax_arrears_cnt": ["tax arrears", "unpaid tax", "tax debt"],
    "tax_violation_cnt": ["tax violations", "tax compliance violations"],
    "customer_concentration": ["customer concentration", "customer dependency"],
    "supplier_concentration": ["supplier concentration", "supplier dependency"],
    "invoice_count": ["invoice count", "number of invoices"],
    "invoice_monthly_avg": ["monthly invoice average", "average monthly invoices"],
    "scenario_loan_readiness": ["loan readiness", "loan eligibility", "can this company get a loan"],
    "scenario_tax_compliance": ["tax compliance", "tax risk", "tax issue"],
    "scenario_invoice_anomaly": ["invoice anomaly", "invoice fraud risk"],
    "scenario_business_stability": ["business stability", "operation stability"],
    "scenario_shell_company_risk": ["shell company risk", "shell company"],
    "scenario_growth_quality": ["growth quality", "quality of growth"],
    "scenario_operating_deterioration": ["operating deterioration", "business deterioration"],
}

NON_TOOL_CORE_FIELDS = {
    "enterprise_id",
    "display_label",
    "display_name",
    "industry_l1",
    "industry_l2",
    "province",
    "city",
    "scale_label",
    "updated_at",
    "has_financial_statements",
}

CORE_FIELD_ALIASES: dict[str, list[str]] = {
    "overall_score": ["综合得分", "综合风险得分", "总体评分"],
    "authenticity_score": ["真实性得分", "经营真实性得分"],
    "finance_score": ["财务健康得分"],
    "invoice_score": ["发票健康得分"],
    "legal_score": ["法律合规得分"],
    "tax_health_score": ["税务健康得分", "税务合规得分"],
    "industry_score": ["和同行比", "同业位置", "行业位置", "在同行中"],
    "fraud_composite_score": ["哪里值得优先核查", "优先核查", "值得优先核查", "该查哪里"],
    "credit_level": ["纳税信用等级", "信用等级"],
    "credit_score": ["纳税信用分", "信用评分"],
    "tax_on_time_rate": [
        "交税情况",
        "纳税情况",
        "纳税准时率",
        "有没有按时缴税",
        "逾期纳税",
    ],
    "tax_arrears_cnt": ["欠税", "欠税多不多", "欠税次数"],
    "tax_violation_cnt": ["税务违法", "违法次数", "涉税违法"],
    "high_severity_cnt": ["重大税务违法", "高危事件"],
    "is_dishonesty": ["是否失信", "失信记录"],
    "is_execution": ["是否被执行", "被执行记录"],
    "loan_cnt": ["贷款笔数", "借款次数"],
    "loan_amount": ["贷款金额", "借款金额"],
    "vat_revenue": ["增值税口径营收", "增值税收入"],
    "invoice_revenue": ["发票口径收入", "开票收入"],
    "finance_revenue": ["财务口径收入", "财务报表收入"],
    "revenue_deviation": ["收入对不上", "营收偏差", "多口径营收差异"],
    "invoice_monthly_avg": ["月均开票", "每月平均开票"],
    "invoice_cnt": ["发票数量", "开票张数", "invoice count"],
    "red_invoice_cnt": ["红字发票", "红冲发票", "红票数量"],
    "social_trend": ["社保趋势", "员工人数趋势"],
    "social_months": ["社保缴了几个月", "社保连续月数"],
    "profit_margin": ["利润率", "盈利水平"],
    "revenue_yoy": ["营收同比", "收入增长", "行业趋势", "各行业趋势", "趋势走向"],
    "profit_yoy": ["利润同比", "利润增长"],
    "debt_ratio": ["资产负债率", "负债率", "债务压力", "杠杆"],
    "cash_flow_net": ["经营现金流净额", "净现金流"],
    "cash_flow_level": ["现金流", "现金流稳不稳", "现金流质量"],
    "current_ratio": ["流动比率", "短期偿债能力"],
    "quick_ratio": ["速动比率", "快速偿债能力"],
    "gross_margin": ["毛利率", "毛利润水平"],
    "net_margin": ["净利率", "净利润水平"],
    "roe": ["净资产收益率", "ROE"],
    "roa": ["总资产收益率", "ROA"],
    "receivables_turnover": ["应收账款周转率", "回款速度"],
    "inventory_turnover": ["存货周转率", "库存周转速度"],
    "asset_turnover": ["总资产周转率", "资产使用效率"],
    "customer_concentration": ["客户集中度", "大客户依赖"],
    "supplier_concentration": ["供应商集中度", "供应商依赖"],
    "category_concentration": ["品目集中度", "商品集中度"],
    "void_invoice_cnt": ["作废发票", "作废发票数量"],
    "unit_price_ratio": ["单价差异", "单价离散度"],
    "vat_burden": ["增值税税负", "增值税负担"],
    "income_tax_burden": ["所得税税负", "所得税负担"],
    "correction_times": ["申报更正次数", "更正过几次"],
    "social_headcount": ["社保人数", "员工人数"],
    "tax_late_penalty_cnt": ["滞纳金", "税务罚款"],
    "change_cnt": ["工商变更", "变更次数"],
}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_metric(
    session: Session,
    *,
    metric_key: str,
    name: str,
    description: str,
    formula: str,
    category: str,
    source_fields: list[str],
    source_tables: list[str],
    aliases: list[str],
    status: str,
    shape: str,
    metric_type: str = "computed",
) -> MetricDefinition:
    rec = session.get(MetricDefinition, metric_key)
    if rec is None:
        rec = MetricDefinition(metric_key=metric_key)
        session.add(rec)
    rec.name = name
    rec.description = description
    rec.metric_type = metric_type
    rec.formula = formula
    rec.unit = ""
    rec.grain = "enterprise"
    rec.source_fields_json = _json(source_fields)
    rec.dimensions_json = _json(["industry_l1", "province", "scale_label", "time"])
    rec.default_filters_json = "{}"
    rec.edge_cases = ""
    rec.is_canonical = metric_key in {m["metric_key"] for m in CANONICAL_METRICS}
    rec.category = category
    rec.version = 1
    rec.status = status
    rec.shape = shape
    rec.retrieval_enabled = status == "validated"
    rec.threshold_required = metric_key in THRESHOLD_REQUIRED_METRICS
    rec.aliases_json = _json(aliases)
    rec.source_tables_json = _json(source_tables)
    rec.updated_at = _now()
    return rec


def _upsert_tool(
    session: Session,
    *,
    tool_id: str,
    kind: str,
    title: str,
    description: str,
    status: str,
    shape: str,
    scenarios: list[str],
    chapter_links: list[str],
    dependencies: list[str],
) -> ToolDefinition:
    tool = session.get(ToolDefinition, tool_id)
    if tool is None:
        tool = ToolDefinition(tool_id=tool_id)
        session.add(tool)
    tool.kind = kind
    tool.title = title
    tool.description = description
    tool.input_schema_json = _json(
        {
            "type": "object",
            "properties": {"entity": {"type": "string"}, "scope": {"type": "string"}},
        }
    )
    tool.output_schema_json = _json({"type": "object"})
    tool.required_params_json = _json(["entity"] if kind == "scenario_tool" else [])
    tool.dependencies_json = _json(dependencies)
    tool.chapter_links_json = _json(chapter_links)
    tool.scenarios_json = _json(scenarios)
    tool.shape = shape
    tool.version = 1
    tool.status = status
    tool.enabled = status == "validated"
    tool.updated_at = _now()
    return tool


def _upsert_alias(
    session: Session,
    *,
    tool_id: str,
    alias: str,
    status: str,
) -> None:
    if not alias.strip():
        return
    existing = (
        session.query(ToolAlias)
        .filter(ToolAlias.tool_id == tool_id, ToolAlias.alias == alias.strip())
        .one_or_none()
    )
    if existing is None:
        existing = ToolAlias(tool_id=tool_id, alias=alias.strip())
        session.add(existing)
    existing.alias_type = "query"
    existing.language = "en" if alias.isascii() else "zh"
    existing.weight = 100
    existing.status = status
    existing.updated_at = _now()


def _upsert_example(
    session: Session,
    *,
    tool_id: str,
    query_text: str,
    status: str,
) -> None:
    existing = (
        session.query(ToolExample)
        .filter(ToolExample.tool_id == tool_id, ToolExample.query_text == query_text)
        .one_or_none()
    )
    if existing is None:
        existing = ToolExample(tool_id=tool_id, query_text=query_text)
        session.add(existing)
    existing.example_type = "positive"
    existing.language = "en" if query_text.isascii() else "zh"
    existing.metadata_json = "{}"
    existing.status = status
    existing.updated_at = _now()


def _upsert_rule(
    session: Session,
    *,
    rule_id: str,
    metric_key: str,
    operator: str,
    value,
    severity: str,
    action: str,
    status: str,
) -> None:
    rule = session.get(ThresholdRule, rule_id)
    if rule is None:
        rule = ThresholdRule(rule_id=rule_id)
        session.add(rule)
    rule.metric_key = metric_key
    rule.scope_json = "{}"
    rule.operator = operator
    rule.threshold_json = _json({"value": value})
    rule.severity = severity
    rule.action = action
    rule.source = "metric_catalog_v2"
    rule.version = 1
    rule.status = status
    rule.enabled = status == "validated"
    rule.updated_at = _now()


def _upsert_dependency(
    session: Session,
    *,
    tool_id: str,
    depends_on_tool_id: str,
) -> None:
    existing = (
        session.query(ToolDependency)
        .filter(
            ToolDependency.tool_id == tool_id,
            ToolDependency.depends_on_tool_id == depends_on_tool_id,
        )
        .one_or_none()
    )
    if existing is None:
        existing = ToolDependency(
            tool_id=tool_id,
            depends_on_tool_id=depends_on_tool_id,
        )
        session.add(existing)
    existing.relation = "requires"
    existing.version = 1
    existing.updated_at = _now()


def _seed_metrics_and_tools(session: Session) -> dict[str, int]:
    core_columns = set(CoreMetrics.__table__.columns.keys())
    canonical = {metric["metric_key"]: metric for metric in CANONICAL_METRICS}
    candidates = {item["metric_key"]: item for item in P0_CANDIDATES}
    core_metric_keys = core_columns - NON_TOOL_CORE_FIELDS
    all_keys = list(
        dict.fromkeys(
            list(canonical)
            + [key for key in core_metric_keys if key not in canonical]
            + [key for key in candidates if key not in canonical and key not in core_metric_keys]
        )
    )
    tool_count = 0
    alias_count = 0

    for metric_key in all_keys:
        canonical_metric = canonical.get(metric_key)
        candidate = candidates.get(metric_key) or {}
        implemented = bool(canonical_metric) or metric_key in core_metric_keys
        status = "validated" if implemented else "planned"
        aliases = list(candidate.get("aliases") or [])
        aliases.extend(CORE_FIELD_ALIASES.get(metric_key, []))
        aliases.extend(MULTILINGUAL_ALIASES.get(metric_key, []))
        deduped_aliases: list[str] = []
        for alias in aliases:
            if alias and alias not in deduped_aliases:
                deduped_aliases.append(alias)
        aliases = deduped_aliases
        title = (
            canonical_metric.get("name")
            if canonical_metric
            else (aliases[0] if aliases else metric_key)
        )
        formula = (
            canonical_metric.get("formula")
            if canonical_metric
            else candidate.get("formula") or ""
        )
        _upsert_metric(
            session,
            metric_key=metric_key,
            name=title,
            description=formula or title,
            formula=formula,
            category=(
                (canonical_metric or {}).get("category")
                or candidate.get("category")
                or ("scenario" if metric_key.startswith("scenario_") else "composite")
            ),
            source_fields=(
                canonical_metric.get("source_fields")
                if canonical_metric
                    else ([metric_key] if metric_key in core_metric_keys else [])
            ),
            source_tables=list(candidate.get("source_tables") or []),
            aliases=aliases,
            status=status,
            shape=(canonical_metric or {}).get("shape") or "single_value",
            metric_type="computed" if canonical_metric else "simple",
        )
        kind = "scenario_tool" if metric_key.startswith("scenario_") else (
            "composite_metric" if canonical_metric else "atomic_metric"
        )
        tool_id = (
            metric_key
            if metric_key.startswith("scenario_")
            else f"metric_{metric_key}"
        )
        _upsert_tool(
            session,
            tool_id=tool_id,
            kind=kind,
            title=title,
            description=formula or title,
            status=status,
            shape=(canonical_metric or {}).get("shape") or "single_value",
            scenarios=["loan", "rating", "warn", "audit"] if kind == "scenario_tool" else [],
            chapter_links=[],
            dependencies=SCENARIO_DEPENDENCIES.get(metric_key, []),
        )
        for dependency in SCENARIO_DEPENDENCIES.get(metric_key, []):
            _upsert_dependency(
                session,
                tool_id=tool_id,
                depends_on_tool_id=dependency,
            )
        tool_count += 1
        for alias in aliases:
            _upsert_alias(session, tool_id=tool_id, alias=alias, status=status)
            _upsert_example(session, tool_id=tool_id, query_text=alias, status=status)
            alias_count += 1

    for key, chapter in CHAPTER_REGISTRY.items():
        tool_id = f"chapter_{key}"
        dependencies = [
            f"metric_{kpi['metric']}"
            for kpi in chapter.get("kpis") or []
            if kpi.get("metric")
        ]
        _upsert_tool(
            session,
            tool_id=tool_id,
            kind="chapter",
            title=chapter["title"],
            description=chapter["desc"],
            status="validated",
            shape="chapter",
            scenarios=[],
            chapter_links=[key],
            dependencies=dependencies,
        )
        tool_count += 1
        for alias in chapter.get("keywords") or []:
            _upsert_alias(session, tool_id=tool_id, alias=alias, status="validated")
            alias_count += 1
        for dependency in dependencies:
            _upsert_dependency(
                session,
                tool_id=tool_id,
                depends_on_tool_id=dependency,
            )
    return {"metrics": len(all_keys), "tools": tool_count, "aliases": alias_count}


def _seed_thresholds(session: Session) -> int:
    count = 0
    for metric_key, cfg in FINANCIAL_RATIOS.items():
        direction = cfg.get("warn_dir")
        value = cfg.get("warn_threshold")
        if direction not in {"gt", "lt"} or value is None:
            continue
        tool = session.get(ToolDefinition, f"metric_{metric_key}")
        status = tool.status if tool else "planned"
        _upsert_rule(
            session,
            rule_id=f"{metric_key}.default.{direction}.{value}.v1",
            metric_key=metric_key,
            operator=direction,
            value=value,
            severity="warn",
            action=f"触发 {metric_key} 风险提示",
            status=status,
        )
        count += 1

    extra_rules = [
        ("revenue_deviation", "gte", REVENUE_DEVIATION_WARN, "核查多口径营收偏差"),
        ("cross_avg_deviation", "gte", CROSS_AVG_DEVIATION_WARN, "核查多源交叉偏差"),
        ("cross_max_deviation", "gte", CROSS_MAX_DEVIATION_WARN, "核查最大口径偏差"),
        ("tax_arrears_cnt", "gt", 0, "核查欠税记录"),
        ("tax_violation_cnt", "gt", 0, "核查税务违法记录"),
        ("tax_on_time_rate", "lt", 0.8, "核查逾期纳税行为"),
    ]
    for metric_key, operator, value, action in extra_rules:
        tool = session.get(ToolDefinition, f"metric_{metric_key}")
        status = tool.status if tool else "planned"
        _upsert_rule(
            session,
            rule_id=f"{metric_key}.default.{operator}.{value}.v1",
            metric_key=metric_key,
            operator=operator,
            value=value,
            severity="warn",
            action=action,
            status=status,
        )
        count += 1
    return count


def seed_semantic_registry(engine: Engine | None = None) -> dict[str, int]:
    if engine is None:
        from app.db.urls import get_sync_engine

        engine = get_sync_engine()
    with Session(engine) as session:
        metrics = _seed_metrics_and_tools(session)
        thresholds = _seed_thresholds(session)
        session.commit()
        return {
            "metrics": metrics["metrics"],
            "tools": metrics["tools"],
            "aliases": metrics["aliases"],
            "thresholds": thresholds,
        }


def main() -> None:
    print(json.dumps(seed_semantic_registry(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
