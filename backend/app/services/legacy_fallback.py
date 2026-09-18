"""Legacy deterministic semantic fallbacks kept outside the LLM-first main path."""
from __future__ import annotations

import re


INDUSTRY_DISTRIBUTION_RE = re.compile(
    r"(哪些|什么|多少).{0,8}行业|行业.{0,8}(划分|分类|分布|清单|有哪些)|按行业"
)

OPEN_OVERVIEW_RE = re.compile(
    r"值得(?:重点)?(?:分析|关注|看)|重点(?:分析|关注|看)|优先(?:分析|关注|核查)|"
    r"从哪里(?:看|查|分析)|哪些(?:方面|问题|风险|指标|点)|"
    r"综合(?:看|分析|评估|概览)|风险(?:画像|概览|体检)|经营(?:画像|概览|体检)|"
    r"有什么(?:问题|风险|异常)|看什么|查什么"
)
COMPARISON_RE = re.compile(r"对比|比较|相比|同比|环比")
TREND_RE = re.compile(r"趋势|走势|变化|近\d+年|逐月|逐年")
DIAGNOSIS_RE = re.compile(r"为什么|原因|归因|诊断|分析一下|怎么回事")
DOMAIN_ANALYSIS_RE = re.compile(
    r"税务|财务|发票|税票|真实性|经营|风险|信用|评级|纳税|开票|收入|利润|现金流|"
    r"资产|负债|指标|数据|行业|行业地位|地位|舞弊|税负|准时率"
)

PATTERN_CANDIDATE_PRIORITY = {
    "stratification": (
        "metric_industry_score",
        "metric_credit_level",
        "metric_overall_score",
        "metric_tax_health_score",
        "metric_authenticity_score",
        "metric_invoice_score",
    ),
    "ranking": (
        "metric_overall_score",
        "metric_credit_level",
        "metric_industry_score",
        "metric_fraud_composite_score",
    ),
    "trend": (
        "metric_revenue_yoy",
        "metric_profit_yoy",
        "metric_tax_on_time_rate",
        "metric_change_cnt",
    ),
    "benchmark": (
        "metric_peer_industry_percentile",
        "metric_industry_score",
        "metric_overall_score",
    ),
    "anomaly": (
        "metric_red_invoice_cnt",
        "metric_tax_arrears_cnt",
        "metric_revenue_deviation",
        "metric_suspicious_count",
    ),
}


def is_industry_distribution_query(query: str) -> bool:
    return bool(INDUSTRY_DISTRIBUTION_RE.search(query or ""))


def prioritize_candidates(candidate_tool_ids: list[str], analysis_pattern: str) -> list[str]:
    priority = list(PATTERN_CANDIDATE_PRIORITY.get(analysis_pattern, ()))
    return [tool_id for tool_id in priority if tool_id in candidate_tool_ids] + [
        tool_id for tool_id in candidate_tool_ids if tool_id not in priority
    ]
