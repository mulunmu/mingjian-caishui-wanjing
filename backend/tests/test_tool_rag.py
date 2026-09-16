from __future__ import annotations

from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.tool_rag import ToolRagRetriever, load_tool_snapshot_sync
from tests.test_semantic_registry_seed import _engine


GOLDEN_QUERIES: list[tuple[str, str]] = [
    ("资产负债率高不高", "metric_debt_ratio"),
    ("这家公司债务压力大不大", "metric_debt_ratio"),
    ("How high is the debt ratio?", "metric_debt_ratio"),
    ("流动比率怎么样", "metric_current_ratio"),
    ("短期偿债能力好不好", "metric_current_ratio"),
    ("速动比率高不高", "metric_quick_ratio"),
    ("现金流稳不稳", "metric_cash_flow_level"),
    ("公司现金流情况如何", "metric_cash_flow_level"),
    ("How is the cash flow?", "metric_cash_flow_level"),
    ("经营现金流净额多少", "metric_cash_flow_net"),
    ("营收增长怎么样", "metric_revenue_yoy"),
    ("收入同比涨了多少", "metric_revenue_yoy"),
    ("Revenue growth?", "metric_revenue_yoy"),
    ("利润同比增长吗", "metric_profit_yoy"),
    ("利润率怎么样", "metric_profit_margin"),
    ("毛利率高不高", "metric_gross_margin"),
    ("净利率是多少", "metric_net_margin"),
    ("ROE 怎么样", "metric_roe"),
    ("净资产收益率高不高", "metric_roe"),
    ("ROA 怎么样", "metric_roa"),
    ("总资产周转率如何", "metric_asset_turnover"),
    ("应收账款周转快不快", "metric_receivables_turnover"),
    ("存货周转率怎么样", "metric_inventory_turnover"),
    ("发票数量有多少", "metric_invoice_cnt"),
    ("Invoice count", "metric_invoice_cnt"),
    ("月均开票多少", "metric_invoice_monthly_avg"),
    ("每月平均开多少票", "metric_invoice_monthly_avg"),
    ("发票口径收入多少", "metric_invoice_revenue"),
    ("增值税口径营收是多少", "metric_vat_revenue"),
    ("财务口径收入多少", "metric_finance_revenue"),
    ("客户是不是太集中", "metric_customer_concentration"),
    ("大客户依赖严重吗", "metric_customer_concentration"),
    ("Customer concentration", "metric_customer_concentration"),
    ("供应商集中度怎么样", "metric_supplier_concentration"),
    ("品目是不是太集中", "metric_category_concentration"),
    ("红字发票有多少", "metric_red_invoice_cnt"),
    ("红冲发票多不多", "metric_red_invoice_cnt"),
    ("作废发票有多少", "metric_void_invoice_cnt"),
    ("单价差异大不大", "metric_unit_price_ratio"),
    ("增值税税负高不高", "metric_vat_burden"),
    ("VAT burden", "metric_vat_burden"),
    ("所得税税负高不高", "metric_income_tax_burden"),
    ("纳税准时率多少", "metric_tax_on_time_rate"),
    ("有没有按时缴税", "metric_tax_on_time_rate"),
    ("欠税多不多", "metric_tax_arrears_cnt"),
    ("Tax arrears", "metric_tax_arrears_cnt"),
    ("税务违法次数多少", "metric_tax_violation_cnt"),
    ("滞纳金和罚款多不多", "metric_tax_late_penalty_cnt"),
    ("申报更正过几次", "metric_correction_times"),
    ("社保人数多少", "metric_social_headcount"),
    ("员工人数是多少", "metric_social_headcount"),
    ("工商变更多不多", "metric_change_cnt"),
    ("社保缴了几个月", "metric_social_months"),
    ("社保趋势怎么样", "metric_social_trend"),
    ("收入对不上吗", "metric_revenue_deviation"),
    ("多口径营收差异大不大", "metric_revenue_deviation"),
    ("综合风险评分多少", "metric_overall_score"),
    ("税务健康得分多少", "metric_tax_health_score"),
    ("经营真实性得分多少", "metric_authenticity_score"),
    ("财务健康得分多少", "metric_finance_score"),
    ("行业地位得分多少", "metric_industry_score"),
    ("法律合规得分多少", "metric_legal_score"),
    ("发票健康得分多少", "metric_invoice_score"),
    ("纳税信用分多少", "metric_credit_score"),
]


def test_tool_rag_meets_recall_gate_on_golden_queries():
    engine = _engine()
    seed_semantic_registry(engine)
    retriever = ToolRagRetriever(load_tool_snapshot_sync(engine))
    hits = 0
    misses: list[tuple[str, str, list[str]]] = []
    for query, expected in GOLDEN_QUERIES:
        ids = [candidate.tool_id for candidate in retriever.retrieve(query, top_k=5)]
        if expected in ids:
            hits += 1
        else:
            misses.append((query, expected, ids))
    recall = hits / len(GOLDEN_QUERIES)
    assert recall >= 0.90, misses


def test_planned_tools_are_not_returned():
    engine = _engine()
    seed_semantic_registry(engine)
    retriever = ToolRagRetriever(load_tool_snapshot_sync(engine))
    ids = {
        candidate.tool_id
        for query in ("能不能贷款", "公司稳不稳", "是不是皮包公司", "发票虚开风险")
        for candidate in retriever.retrieve(query, top_k=10)
    }
    assert "scenario_loan_readiness" not in ids
    assert "scenario_business_stability" not in ids
    assert "scenario_shell_company_risk" not in ids
    assert "scenario_invoice_anomaly" not in ids


def test_executable_only_retrieval_filters_unregistered_tools():
    engine = _engine()
    seed_semantic_registry(engine)
    retriever = ToolRagRetriever(load_tool_snapshot_sync(engine))
    ids = [
        candidate.tool_id
        for candidate in retriever.retrieve(
            "现金流稳不稳",
            top_k=10,
            executable_only=True,
        )
    ]
    assert "metric_debt_ratio" in retriever.retrieve(
        "资产负债率高不高",
        top_k=10,
        executable_only=True,
    )[0].tool_id
    assert "metric_cash_flow_level" in ids
    assert "metric_zero_declaration_months" not in retriever.retrieve(
        "长期零申报",
        top_k=10,
        executable_only=True,
    )
