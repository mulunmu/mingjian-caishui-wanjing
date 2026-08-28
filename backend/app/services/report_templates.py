"""报告场景模板：场景 × (维度×功能) 章节"""
from __future__ import annotations

import os
from typing import Any

# 每章：功能是什么 → 由 judgment 填结论 → 证据链来自 claim.trace
ChapterSpec = dict[str, Any]

SCENARIOS: dict[str, dict[str, Any]] = {
    "general": {
        "title": "行业趋势风控报告",
        "tier": "general",
        "story": "面向通识读者，讲清样本覆盖、行业走向与主要风险信号。",
        "chapters": [
            {
                "function": "trend",
                "dimension": "industry",
                "title": "行业趋势",
                "purpose": "描述各行业大类营收同比与社保趋势，刻画上行/平稳/下行。",
            },
            {
                "function": "score",
                "dimension": "industry",
                "title": "信用与纳税健康",
                "purpose": "按行业汇总信用分与纳税准时率，形成可比基准。",
            },
            {
                "function": "signal",
                "dimension": "signal",
                "title": "风险信号总览",
                "purpose": "汇总失信、被执行、高偏差与低信用等级的切片分布。",
            },
            {
                "function": "authenticity",
                "dimension": "overall",
                "title": "经营真实性",
                "purpose": "多源营收交叉验证与 Benford 数字分布检验。",
            },
        ],
    },
    "fraud": {
        "title": "欺诈与发票异常风控报告",
        "tier": "general",
        "story": "聚焦进销错配、红冲、集中度与异常检测信号。",
        "chapters": [
            {
                "function": "fraud",
                "dimension": "industry",
                "title": "发票舞弊切片",
                "purpose": "基于发票明细的 scbm 错配、红字、集中度与序列缺口。",
            },
            {
                "function": "authenticity",
                "dimension": "overall",
                "title": "真实性交叉验证",
                "purpose": "增值税/发票/财报口径偏差与 Benford 检验。",
            },
            {
                "function": "signal",
                "dimension": "signal",
                "title": "关联风险信号",
                "purpose": "司法失信与高偏差主体在行业中的集中情况。",
            },
        ],
    },
    "due_diligence": {
        "title": "尽调组合风险报告",
        "tier": "general",
        "story": "尽调视角覆盖评分、真实性、舞弊与同业对标。",
        "chapters": [
            {"function": "score", "dimension": "industry", "title": "综合评分切片", "purpose": "行业信用与纳税健康。"},
            {"function": "authenticity", "dimension": "overall", "title": "真实性", "purpose": "交叉验证与 Benford。"},
            {"function": "fraud", "dimension": "overall", "title": "舞弊检测", "purpose": "发票异常信号汇总。"},
            {"function": "benchmark", "dimension": "industry", "title": "行业对标", "purpose": "industry_benchmark 基准对照。"},
            {"function": "signal", "dimension": "signal", "title": "预警清单", "purpose": "高风险信号计数。"},
        ],
    },
    "fundamental": {
        "title": "基本面趋势报告",
        "tier": "general",
        "story": "侧重同比趋势与行业基准，少涉舞弊细节。",
        "chapters": [
            {"function": "trend", "dimension": "industry", "title": "趋势走向", "purpose": "营收同比与增长/缩减结构。"},
            {"function": "benchmark", "dimension": "industry", "title": "行业基准", "purpose": "均值与高风险占比。"},
            {"function": "score", "dimension": "region", "title": "地区评分", "purpose": "分省份信用分对比。"},
        ],
    },
    "custom": {
        "title": "定制深度风控报告",
        "tier": "premium",
        "story": "按需组合全维度切片：地区对比、行业趋势、真实性、舞弊、对标与预警。",
        "chapters": [
            {"function": "score", "dimension": "region", "title": "地区评分对比", "purpose": "分省份信用分对比与极差。"},
            {"function": "trend", "dimension": "industry", "title": "行业趋势走向", "purpose": "营收同比与社保趋势。"},
            {"function": "authenticity", "dimension": "overall", "title": "经营真实性", "purpose": "多源交叉验证与 Benford。"},
            {"function": "fraud", "dimension": "industry", "title": "发票舞弊切片", "purpose": "scbm 错配、红冲、集中度与序列缺口。"},
            {"function": "benchmark", "dimension": "industry", "title": "行业对标", "purpose": "行业基准对照。"},
            {"function": "signal", "dimension": "signal", "title": "风险预警清单", "purpose": "高风险信号计数与分布。"},
        ],
    },
}

# 场景中文名（含付费层级提示）
SCENARIO_LABELS = {
    "general": "行业趋势风控（通用）",
    "fraud": "欺诈舞弊风控（通用）",
    "due_diligence": "尽调组合（通用）",
    "fundamental": "基本面趋势（通用）",
    "custom": "定制深度风控（付费）",
}

# 对话快捷：「生成报告」默认通识；可指定场景关键词
SCENARIO_ALIASES = {
    "通识": "general",
    "趋势": "general",
    "欺诈": "fraud",
    "舞弊": "fraud",
    "尽调": "due_diligence",
    "基本面": "fundamental",
    "定制": "custom",
    "专属": "custom",
    "自定义": "custom",
    "custom": "custom",
}


def resolve_scenario(query: str | None = None, scenario: str | None = None) -> str:
    if scenario:
        if scenario in SCENARIOS:
            return scenario
        # 显式传入未知 scenario 时不再静默回退，便于调用方发现拼写错误
        raise ValueError(f"未知报告场景: {scenario}；可选: {', '.join(sorted(SCENARIOS))}")
    q = query or ""
    for kw, key in SCENARIO_ALIASES.items():
        if kw in q:
            return key
    return "general"


def get_scenario(key: str) -> dict[str, Any]:
    return SCENARIOS.get(key) or SCENARIOS["general"]


def get_scenario_tier(key: str) -> str:
    """通用模板 general（免费） vs 定制 premium（付费）。"""
    return (SCENARIOS.get(key) or SCENARIOS["general"]).get("tier", "general")


def get_scenario_label(key: str) -> str:
    return SCENARIO_LABELS.get(key, key)


class PremiumReportLocked(Exception):
    """定制报告（付费层级）在开发期被隔离，尚未开放。"""


def is_premium_locked() -> bool:
    """开发期付费隔离开关。

    默认锁定（false）：premium 场景仅展示层级、不产出报告。
    上线后置 ``PREMIUM_REPORT_ENABLED=true`` 即可开放付费定制链路。
    """
    return os.getenv("PREMIUM_REPORT_ENABLED", "false").lower() not in ("1", "true", "yes")
