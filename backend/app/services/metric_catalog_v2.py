"""Metric Catalog v2 definitions and coverage audit."""
from __future__ import annotations

import json

from app.models.core_metrics import CoreMetrics
from app.services.metric_registry import CANONICAL_METRICS, SOURCE_FIELDS


def _candidate(
    metric_key: str,
    formula: str,
    source_tables: list[str],
    aliases: list[str],
    *,
    category: str,
    grain: str = "enterprise",
    priority: str = "P0",
) -> dict:
    return {
        "metric_key": metric_key,
        "category": category,
        "formula": formula,
        "source_tables": source_tables,
        "aliases": aliases,
        "grain": grain,
        "priority": priority,
    }


P0_CANDIDATES: list[dict] = [
    _candidate("enterprise_age_years", "评估日 - 成立日期", ["syx_enterprise_info"], ["成立多久", "开了几年", "企业年龄"], category="profile"),
    _candidate("registered_capital", "注册资本", ["syx_enterprise_info"], ["注册资本", "注册资金"], category="profile"),
    _candidate("employee_count", "最新员工人数", ["syx_enterprise_info"], ["员工多少", "公司规模"], category="profile"),
    _candidate("taxpayer_type", "纳税主体类型", ["syx_enterprise_info", "syx_taxpayer_type"], ["一般纳税人", "纳税人类型"], category="profile"),
    _candidate("operation_status", "经营状态", ["syx_enterprise_info"], ["还在经营吗", "是否存续"], category="profile"),
    _candidate("change_count", "变更登记次数", ["syx_enterprise_change_info"], ["变更多不多", "工商变更"], category="profile"),
    _candidate("business_scope_change_count", "经营范围变更次数", ["syx_enterprise_change_info"], ["经营内容变没变", "范围变更"], category="profile"),
    _candidate("invoice_amount_total", "SUM(发票金额)", ["syx_invoice", "syx_invoice_details"], ["开票总额", "开票规模", "开了多少票"], category="invoice"),
    _candidate("invoice_tax_amount", "SUM(发票税额)", ["syx_invoice"], ["发票税额", "销项税额"], category="invoice"),
    _candidate("invoice_cnt", "COUNT(发票)", ["syx_invoice"], ["开票张数", "发票数量"], category="invoice"),
    _candidate("invoice_monthly_avg", "开票金额 / 月份数", ["syx_invoice"], ["月均开票", "每月开票多少"], category="invoice"),
    _candidate("invoice_continuity_months", "有开票月份的最长连续段", ["syx_invoice"], ["开票连续吗", "有没有断档"], category="invoice"),
    _candidate("invoice_gap_months", "分析周期内无开票月份数", ["syx_invoice"], ["断票几个月", "开票空窗"], category="invoice"),
    _candidate("red_invoice_amount_ratio", "红字发票金额 / 全部发票金额", ["syx_red_invoices_info", "syx_invoice"], ["红票比例", "冲红多不多"], category="invoice"),
    _candidate("red_invoice_count_ratio", "红字发票张数 / 全部发票张数", ["syx_red_invoices_info", "syx_invoice"], ["红票张数", "冲红次数"], category="invoice"),
    _candidate("invalid_invoice_ratio", "失效发票数 / 全部发票数", ["syx_invoice"], ["无效发票", "发票失效"], category="invoice"),
    _candidate("void_invoice_ratio", "作废发票数 / 全部发票数", ["syx_invoice"], ["作废率", "作废发票多不多"], category="invoice"),
    _candidate("invoice_check_exception_rate", "查验异常发票数 / 已查验发票数", ["syx_invoice"], ["查验异常", "发票核验不过"], category="invoice"),
    _candidate("invoice_risk_high_ratio", "高风险发票数 / 全部发票数", ["syx_invoice"], ["高风险发票", "发票风险"], category="invoice"),
    _candidate("customer_count", "COUNT(DISTINCT 购方)", ["syx_invoice"], ["客户数量", "有多少客户"], category="counterparty"),
    _candidate("supplier_count", "COUNT(DISTINCT 销方)", ["syx_invoice"], ["供应商数量", "有多少供应商"], category="counterparty"),
    _candidate("customer_concentration", "最大客户金额 / 客户交易总额", ["syx_invoice"], ["最大客户占比", "大客户依赖"], category="counterparty"),
    _candidate("customer_top5_concentration", "前五大客户金额 / 客户交易总额", ["syx_invoice"], ["前五客户占比", "客户集中度"], category="counterparty"),
    _candidate("supplier_concentration", "最大供应商金额 / 供应商交易总额", ["syx_invoice"], ["最大供应商占比", "供应商依赖"], category="counterparty"),
    _candidate("supplier_top5_concentration", "前五大供应商金额 / 供应商交易总额", ["syx_invoice"], ["前五供应商占比", "供应商集中度"], category="counterparty"),
    _candidate("customer_hhi", "SUM((客户金额/客户交易总额)^2)", ["syx_invoice"], ["客户HHI", "客户分散度"], category="counterparty"),
    _candidate("supplier_hhi", "SUM((供应商金额/供应商交易总额)^2)", ["syx_invoice"], ["供应商HHI", "供应商分散度"], category="counterparty"),
    _candidate("new_customer_ratio", "本期新增客户数 / 客户总数", ["syx_invoice"], ["新增客户", "新客户多不多"], category="counterparty"),
    _candidate("new_supplier_ratio", "本期新增供应商数 / 供应商总数", ["syx_invoice"], ["新增供应商", "新供应商多不多"], category="counterparty"),
    _candidate("cross_region_invoice_ratio", "跨地区交易金额 / 交易总额", ["syx_invoice"], ["跨地区开票", "异地交易"], category="counterparty"),
    _candidate("unit_price_ratio", "最高单价 / 平均单价", ["syx_invoice_details"], ["单价差异", "价格波动"], category="invoice"),
    _candidate("vat_declared_revenue", "SUM(增值税申报收入)", ["syx_tax_value_added"], ["申报收入", "增值税收入"], category="tax"),
    _candidate("vat_output_tax", "SUM(销项税额)", ["syx_tax_value_added"], ["销项税", "销项税额"], category="tax"),
    _candidate("vat_input_tax", "SUM(进项税额)", ["syx_tax_value_added"], ["进项税", "进项税额"], category="tax"),
    _candidate("vat_burden", "应纳增值税 / 增值税销售收入", ["syx_tax_value_added"], ["增值税税负", "税负高不高"], category="tax"),
    _candidate("vat_burden_volatility", "月度税负率标准差", ["syx_tax_value_added"], ["税负波动", "税负稳定吗"], category="tax"),
    _candidate("zero_declaration_months", "零申报月份数", ["syx_tax_value_added"], ["零申报", "长期零申报"], category="tax"),
    _candidate("income_tax_burden", "所得税额 / 利润总额", ["syx_corporate_income_year"], ["所得税税负", "所得税负担"], category="tax"),
    _candidate("income_tax_effective_rate", "所得税额 / 应纳税所得额", ["syx_corporate_income_year"], ["实际所得税率", "有效税率"], category="tax"),
    _candidate("tax_on_time_rate", "按期缴款次数 / 缴款总次数", ["syx_tax_payment"], ["准时纳税", "有没有逾期"], category="tax"),
    _candidate("tax_arrears_amount", "SUM(欠税应补税额)", ["syx_vat_arrears_tax"], ["欠了多少钱", "欠税金额"], category="tax"),
    _candidate("tax_arrears_cnt", "COUNT(欠税记录)", ["syx_vat_arrears_tax"], ["欠税多不多", "欠税次数"], category="tax"),
    _candidate("tax_late_days_avg", "AVG(缴款日期 - 缴款期限)", ["syx_tax_payment"], ["平均晚几天", "平均逾期"], category="tax"),
    _candidate("tax_late_days_max", "MAX(缴款日期 - 缴款期限)", ["syx_tax_payment"], ["最长逾期", "最晚缴税"], category="tax"),
    _candidate("correction_amount_ratio", "更正涉及税额 / 申报税额", ["syx_declaration_correction"], ["更正金额", "申报改动大不大"], category="tax"),
    _candidate("correction_times", "COUNT(申报更正)", ["syx_declaration_correction"], ["申报改过几次", "更正频率"], category="tax"),
    _candidate("violation_recency_days", "当前日期 - 最近违法日期", ["syx_tax_illega"], ["最近违规", "多久没违规"], category="legal"),
    _candidate("social_headcount", "最新社保缴费人数", ["syx_social_declaration"], ["社保人数", "员工多少"], category="social"),
    _candidate("social_headcount_trend", "近三期社保人数斜率", ["syx_social_declaration"], ["人数趋势", "员工变多还是变少"], category="social"),
    _candidate("social_payment_ratio", "实缴社保 / 应缴社保", ["syx_social_declaration"], ["社保缴足了吗", "社保欠缴"], category="social"),
    _candidate("current_ratio", "流动资产 / 流动负债", ["syx_tax_finance_balance_year", "syx_tax_finance_balance_season"], ["流动比率", "短期偿债能力"], category="financial"),
    _candidate("quick_ratio", "(流动资产-存货) / 流动负债", ["syx_tax_finance_balance_year", "syx_tax_finance_balance_season"], ["速动比率", "快速偿债能力"], category="financial"),
    _candidate("debt_ratio", "负债总额 / 资产总额", ["syx_tax_finance_balance_year", "syx_tax_finance_balance_season"], ["资产负债率", "负债高不高"], category="financial"),
    _candidate("gross_margin", "毛利 / 营业收入", ["syx_tax_finance_profit_year", "syx_tax_finance_profit_season"], ["毛利率", "赚钱能力"], category="financial"),
    _candidate("net_margin", "净利润 / 营业收入", ["syx_tax_finance_profit_year", "syx_tax_finance_profit_season"], ["净利率", "净赚多少"], category="financial"),
    _candidate("roe", "净利润 / 净资产", ["syx_tax_finance_balance_year", "syx_tax_finance_profit_year"], ["净资产收益率", "ROE"], category="financial"),
    _candidate("roa", "净利润 / 总资产", ["syx_tax_finance_balance_year", "syx_tax_finance_profit_year"], ["总资产收益率", "ROA"], category="financial"),
    _candidate("ocf_to_revenue", "经营现金流 / 营业收入", ["syx_cash_flow", "syx_tax_finance_profit_year"], ["现金流质量", "收现能力"], category="financial"),
    _candidate("cash_flow_volatility", "经营现金流标准差 / 收入均值", ["syx_cash_flow"], ["现金流稳不稳", "现金流波动"], category="financial"),
    _candidate("scenario_operating_deterioration", "收入、利润、现金流、社保、开票趋势综合评分", ["multiple"], ["经营变差了吗", "有没有恶化"], category="scenario"),
    _candidate("scenario_business_stability", "存续、变更、社保、开票连续性和收入稳定性综合评分", ["multiple"], ["稳不稳", "靠不靠谱"], category="scenario"),
    _candidate("scenario_shell_company_risk", "社保、开票、收入、存续和变更行为综合评分", ["multiple"], ["空壳", "皮包公司"], category="scenario"),
    _candidate("scenario_invoice_anomaly", "红票、作废、失效、集中度、价格和新增交易对手综合评分", ["multiple"], ["发票异常", "虚开风险"], category="scenario"),
    _candidate("scenario_tax_compliance", "税负、欠税、违法、更正和缴纳行为综合评分", ["multiple"], ["税务合规", "涉税风险"], category="scenario"),
    _candidate("scenario_loan_readiness", "偿债、现金流、税务合规、经营稳定性和事件风险综合评分", ["multiple"], ["能不能贷款", "授信"], category="scenario"),
    _candidate("scenario_growth_quality", "收入、利润、现金流和开票增长质量综合评分", ["multiple"], ["增长质量", "增长健康吗"], category="scenario"),
]


def build_metric_catalog_audit() -> dict:
    core_columns = set(CoreMetrics.__table__.columns.keys())
    canonical = {metric["metric_key"] for metric in CANONICAL_METRICS}
    source_fields = {field["field"] for field in SOURCE_FIELDS}
    return {
        "counts": {
            "core_columns": len(core_columns),
            "canonical_metrics": len(canonical),
            "source_fields": len(source_fields),
            "p0_candidates": len(P0_CANDIDATES),
        },
        "missing_from_canonical": sorted(core_columns - canonical),
        "source_fields_missing_from_core": sorted(source_fields - core_columns),
        "p0_candidates": P0_CANDIDATES,
    }


def main() -> None:
    print(json.dumps(build_metric_catalog_audit(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
