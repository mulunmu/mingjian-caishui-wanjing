"""Stage 17 metric support catalog derived from real PostgreSQL fields."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage17MetricSpec:
    metric_key: str
    name: str
    formula: str
    unit: str
    source_tables: tuple[str, ...]
    source_fields: tuple[str, ...]
    aliases: tuple[str, ...]
    shape: str = "single_value"


@dataclass(frozen=True)
class Stage17UnsupportedSpec:
    metric_key: str
    reason: str
    missing_source: str


def _spec(
    metric_key: str,
    name: str,
    formula: str,
    unit: str,
    source_table: str,
    source_fields: tuple[str, ...],
    aliases: tuple[str, ...],
    *,
    shape: str = "single_value",
) -> Stage17MetricSpec:
    return Stage17MetricSpec(
        metric_key=metric_key,
        name=name,
        formula=formula,
        unit=unit,
        source_tables=(source_table,),
        source_fields=source_fields,
        aliases=aliases,
        shape=shape,
    )


SUPPORTED_EXTENDED_METRICS: dict[str, Stage17MetricSpec] = {
    "customer_count": _spec(
        "customer_count",
        "客户数量",
        "enterprise_invoice_profile.customer_count",
        "家",
        "enterprise_invoice_profile",
        ("customer_count",),
        ("客户数量", "有多少客户", "客户家数"),
    ),
    "customer_hhi": _spec(
        "customer_hhi",
        "客户HHI",
        "enterprise_invoice_profile.customer_hhi",
        "",
        "enterprise_invoice_profile",
        ("customer_hhi",),
        ("客户HHI", "客户集中指数", "客户分散度"),
    ),
    "customer_top5_concentration": _spec(
        "customer_top5_concentration",
        "前五客户占比",
        "sum(top_customers_json[].share)，缺失时回退 top_customer_share",
        "%",
        "enterprise_invoice_profile",
        ("top_customers_json", "top_customer_share"),
        ("前五客户占比", "大客户占比", "客户集中度前五"),
    ),
    "income_tax_effective_rate": _spec(
        "income_tax_effective_rate",
        "实际所得税率",
        "enterprise_financials.income_tax / enterprise_financials.total_profit（仅利润总额 > 0）",
        "%",
        "enterprise_financials",
        ("income_tax", "total_profit"),
        ("实际所得税率", "所得税实际税率", "所得税负担"),
    ),
    "invalid_invoice_ratio": _spec(
        "invalid_invoice_ratio",
        "异常凭证占比",
        "abnormal_invoice_cnt / (sales_invoice_cnt + purchase_invoice_cnt)",
        "%",
        "enterprise_invoice_profile",
        ("abnormal_invoice_cnt", "sales_invoice_cnt", "purchase_invoice_cnt"),
        ("无效发票", "异常凭证占比", "异常发票比例"),
    ),
    "ocf_to_revenue": _spec(
        "ocf_to_revenue",
        "现金流质量",
        "operating_cf / revenue（仅 revenue != 0）",
        "%",
        "enterprise_financials",
        ("operating_cf", "revenue"),
        ("现金流质量", "经营现金流占比", "现金流收入比"),
    ),
    "red_invoice_count_ratio": _spec(
        "red_invoice_count_ratio",
        "红票张数比例",
        "red_invoice_cnt / sales_invoice_cnt（仅分母 > 0）",
        "%",
        "enterprise_invoice_profile",
        ("red_invoice_cnt", "sales_invoice_cnt"),
        ("红票比例", "红字发票比例", "红冲张数比例"),
    ),
    "supplier_count": _spec(
        "supplier_count",
        "供应商数量",
        "enterprise_invoice_profile.supplier_count",
        "家",
        "enterprise_invoice_profile",
        ("supplier_count",),
        ("供应商数量", "有多少供应商", "供应商家数"),
    ),
    "supplier_hhi": _spec(
        "supplier_hhi",
        "供应商HHI",
        "enterprise_invoice_profile.supplier_hhi",
        "",
        "enterprise_invoice_profile",
        ("supplier_hhi",),
        ("供应商HHI", "供应商集中指数", "供应商分散度"),
    ),
    "supplier_top5_concentration": _spec(
        "supplier_top5_concentration",
        "前五供应商占比",
        "sum(top_suppliers_json[].share)，缺失时回退 top_supplier_share",
        "%",
        "enterprise_invoice_profile",
        ("top_suppliers_json", "top_supplier_share"),
        ("前五供应商占比", "大供应商占比", "供应商集中度前五"),
    ),
    "violation_recency_days": _spec(
        "violation_recency_days",
        "最近违规距今天数",
        "current_date - max(legal_events.event_date)",
        "天",
        "legal_events",
        ("event_date",),
        ("最近违规", "距上次违法多久", "违规距今"),
    ),
    "void_invoice_ratio": _spec(
        "void_invoice_ratio",
        "作废率",
        "void_invoice_cnt / (sales_invoice_cnt + purchase_invoice_cnt)",
        "%",
        "enterprise_invoice_profile",
        ("void_invoice_cnt", "sales_invoice_cnt", "purchase_invoice_cnt"),
        ("作废率", "作废发票比例", "发票作废占比"),
    ),
}


CROSS_DEVIATION_METRICS: dict[str, Stage17MetricSpec] = {
    "cross_avg_deviation": _spec(
        "cross_avg_deviation",
        "多口径平均偏差",
        "均值(vat_revenue, invoice_revenue, finance_revenue 两两偏差)",
        "",
        "core_metrics",
        ("vat_revenue", "invoice_revenue", "finance_revenue"),
        ("多口径平均偏差", "口径平均偏差", "交叉平均偏差"),
    ),
    "cross_max_deviation": _spec(
        "cross_max_deviation",
        "多口径最大偏差",
        "max(vat_revenue, invoice_revenue, finance_revenue 两两偏差)",
        "",
        "core_metrics",
        ("vat_revenue", "invoice_revenue", "finance_revenue"),
        ("多口径最大偏差", "口径最大偏差", "交叉最大偏差"),
    ),
}


def _unsupported(metric_key: str, reason: str, missing_source: str) -> Stage17UnsupportedSpec:
    return Stage17UnsupportedSpec(metric_key=metric_key, reason=reason, missing_source=missing_source)


UNSUPPORTED_METRICS: dict[str, Stage17UnsupportedSpec] = {
    "business_scope_change_count": _unsupported("business_scope_change_count", "当前仅有变更总次数，没有经营范围变更事件明细。", "business scope change event table"),
    "cash_flow_volatility": _unsupported("cash_flow_volatility", "企业财务表当前一企业一期，无法计算多年现金流标准差。", "multi-period operating cash flow series"),
    "change_count": _unsupported("change_count", "与已验证的 change_cnt 同源重复，避免注册两个口径相同的能力。", "duplicate of change_cnt"),
    "correction_amount_ratio": _unsupported("correction_amount_ratio", "现有数据只有更正次数和记录数，没有更正涉及税额及申报税额分母。", "correction amount and declared tax amount"),
    "cross_region_invoice_ratio": _unsupported("cross_region_invoice_ratio", "发票画像没有交易地区维度，无法区分跨地区交易金额。", "invoice transaction region"),
    "employee_count": _unsupported("employee_count", "当前只有社保缴费人数，没有独立员工人数或用工人数。", "employee headcount"),
    "enterprise_age_years": _unsupported("enterprise_age_years", "没有成立日期或登记存续起始日期。", "establishment date"),
    "invoice_check_exception_rate": _unsupported("invoice_check_exception_rate", "没有已查验发票数和查验异常发票数。", "invoice verification status"),
    "invoice_amount_total": _unsupported("invoice_amount_total", "与已验证的 invoice_revenue 同源重复，避免重复注册销项开票金额。", "duplicate of invoice_revenue"),
    "invoice_continuity_months": _unsupported("invoice_continuity_months", "没有逐月开票序列，无法计算最长连续开票月份。", "monthly invoice series"),
    "invoice_gap_months": _unsupported("invoice_gap_months", "没有逐月开票序列，无法计算断票月份数。", "monthly invoice series"),
    "invoice_risk_high_ratio": _unsupported("invoice_risk_high_ratio", "没有逐票 risk_level 高风险发票数量。", "invoice risk-level detail"),
    "invoice_tax_amount": _unsupported("invoice_tax_amount", "发票画像只保留价税合计，没有单独的发票税额。", "invoice tax amount"),
    "new_customer_ratio": _unsupported("new_customer_ratio", "没有客户期间对比或新增客户标记。", "customer period comparison"),
    "new_supplier_ratio": _unsupported("new_supplier_ratio", "没有供应商期间对比或新增供应商标记。", "supplier period comparison"),
    "operation_status": _unsupported("operation_status", "没有登记经营状态字段。", "registration operation status"),
    "red_invoice_amount_ratio": _unsupported("red_invoice_amount_ratio", "只有红字发票张数，没有红字发票金额。", "red invoice amount"),
    "registered_capital": _unsupported("registered_capital", "当前画像和财务表没有注册资本字段。", "registered capital"),
    "scenario_business_stability": _unsupported("scenario_business_stability", "依赖存续状态、逐月开票、收入稳定性，当前缺少完整时序。", "operation status and time-series stability inputs"),
    "scenario_growth_quality": _unsupported("scenario_growth_quality", "缺少现金流同比、开票增长等完整增长序列。", "cash flow growth and invoice growth series"),
    "scenario_invoice_anomaly": _unsupported("scenario_invoice_anomaly", "缺少新增交易对手、逐票高风险和红字金额等组成部分。", "complete invoice anomaly inputs"),
    "scenario_loan_readiness": _unsupported("scenario_loan_readiness", "依赖经营稳定性、完整事件窗口和现金流质量，当前输入不完整。", "complete loan-readiness inputs"),
    "scenario_operating_deterioration": _unsupported("scenario_operating_deterioration", "缺少现金流、开票和社保的多年时序。", "multi-period operating indicators"),
    "scenario_shell_company_risk": _unsupported("scenario_shell_company_risk", "缺少存续状态、逐月开票和收入稳定性输入。", "shell-company risk inputs"),
    "scenario_tax_compliance": _unsupported("scenario_tax_compliance", "当前缺少统一、可审计的税负目标与更正金额口径，不能用主观权重合成。", "tax compliance scoring specification"),
    "social_headcount_trend": _unsupported("social_headcount_trend", "只有最新社保人数和趋势分类，没有近三期人数序列。", "social headcount period series"),
    "social_payment_ratio": _unsupported("social_payment_ratio", "没有应缴社保金额或实缴差额字段。", "social payable and paid amount"),
    "tax_arrears_amount": _unsupported("tax_arrears_amount", "当前只有欠税条数，没有欠税应补金额。", "tax arrears amount"),
    "tax_late_days_avg": _unsupported("tax_late_days_avg", "没有缴款日期和缴款期限明细。", "tax payment due/actual dates"),
    "tax_late_days_max": _unsupported("tax_late_days_max", "没有缴款日期和缴款期限明细。", "tax payment due/actual dates"),
    "taxpayer_type": _unsupported("taxpayer_type", "没有一般纳税人/小规模纳税人资格类型字段。", "taxpayer qualification type"),
    "vat_burden_volatility": _unsupported("vat_burden_volatility", "没有月度增值税税负序列。", "monthly VAT burden series"),
    "vat_input_tax": _unsupported("vat_input_tax", "税务画像没有进项税额字段。", "VAT input tax"),
    "vat_declared_revenue": _unsupported("vat_declared_revenue", "与已验证的 vat_revenue 同源重复，避免重复注册申报收入。", "duplicate of vat_revenue"),
    "vat_output_tax": _unsupported("vat_output_tax", "税务画像没有销项税额字段。", "VAT output tax"),
    "zero_declaration_months": _unsupported("zero_declaration_months", "没有逐月申报状态序列。", "monthly declaration status series"),
}


SUPPORTED_METRIC_KEYS: set[str] = set(SUPPORTED_EXTENDED_METRICS) | set(CROSS_DEVIATION_METRICS)


def all_stage17_specs() -> dict[str, Stage17MetricSpec]:
    return {**SUPPORTED_EXTENDED_METRICS, **CROSS_DEVIATION_METRICS}
