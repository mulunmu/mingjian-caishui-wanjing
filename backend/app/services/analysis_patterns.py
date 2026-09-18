"""Canonical analysis patterns shared by dialogue and reports.

The registry is deterministic. LLMs may classify language, but the selectable
analysis space, evidence expectations and report block contracts remain explicit
and testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnalysisPatternSpec:
    key: str
    label: str
    description: str
    task_type: str
    block_kind: str
    min_candidates: int = 2
    requires_time: bool = False
    keywords: tuple[str, ...] = ()


ANALYSIS_PATTERNS: dict[str, AnalysisPatternSpec] = {
    "trend": AnalysisPatternSpec(
        key="trend",
        label="趋势",
        description="时间序列、变化速度、拐点与连续性",
        task_type="trend",
        block_kind="trend_paragraph",
        requires_time=True,
        keywords=("趋势", "走势", "时间序列", "变化速度", "拐点", "连续", "同比", "环比"),
    ),
    "structure": AnalysisPatternSpec(
        key="structure",
        label="结构",
        description="占比、构成与集中度",
        task_type="distribution",
        block_kind="comparison_paragraph",
        keywords=("结构", "占比", "构成", "集中度", "组成", "份额"),
    ),
    "distribution": AnalysisPatternSpec(
        key="distribution",
        label="分布",
        description="分箱、集中区间、长尾与异常值",
        task_type="distribution",
        block_kind="comparison_paragraph",
        keywords=("分布", "分箱", "区间", "长尾", "异常值", "离散", "直方"),
    ),
    "ranking": AnalysisPatternSpec(
        key="ranking",
        label="排名",
        description="TopN、分位与排序变化",
        task_type="ranking",
        block_kind="comparison_paragraph",
        keywords=("排名", "排行", "top", "前十", "最大", "最高", "最低", "分位"),
    ),
    "contribution": AnalysisPatternSpec(
        key="contribution",
        label="贡献",
        description="总额变化贡献与因素贡献",
        task_type="contribution",
        block_kind="comparison_paragraph",
        keywords=("贡献", "拉动", "拖累", "增量来自", "因素贡献", "变化贡献"),
    ),
    "attribution": AnalysisPatternSpec(
        key="attribution",
        label="归因",
        description="风险驱动、根因与因果候选",
        task_type="diagnosis",
        block_kind="synthesis_paragraph",
        keywords=("归因", "根因", "原因", "驱动", "为什么", "导致", "因果"),
    ),
    "anomaly": AnalysisPatternSpec(
        key="anomaly",
        label="异常",
        description="阈值、基线、离群与突变",
        task_type="diagnosis",
        block_kind="comparison_paragraph",
        keywords=("异常", "离群", "突变", "越线", "超阈", "预警", "不对劲", "可疑"),
    ),
    "correlation": AnalysisPatternSpec(
        key="correlation",
        label="相关性",
        description="指标关系、共变与相关强弱",
        task_type="correlation",
        block_kind="comparison_paragraph",
        keywords=("相关", "共变", "关系", "联动", "关联"),
    ),
    "stratification": AnalysisPatternSpec(
        key="stratification",
        label="分层",
        description="行业、地区、规模与客户分层",
        task_type="distribution",
        block_kind="comparison_paragraph",
        keywords=("分层", "分组", "按行业", "按地区", "按区域", "按规模", "客户层"),
    ),
    "benchmark": AnalysisPatternSpec(
        key="benchmark",
        label="基准",
        description="行业基准、区域基准与历史基准",
        task_type="benchmark",
        block_kind="comparison_paragraph",
        keywords=("基准", "对标", "同业", "同行", "行业均值", "区域均值", "历史基线"),
    ),
    "scenario": AnalysisPatternSpec(
        key="scenario",
        label="情景模拟",
        description="假设变化与敏感性",
        task_type="scenario",
        block_kind="synthesis_paragraph",
        keywords=("情景", "假设", "敏感", "如果", "若", "压力测试", "模拟"),
    ),
    "drilldown": AnalysisPatternSpec(
        key="drilldown",
        label="下钻",
        description="从结论追到指标、期间与明细",
        task_type="drilldown",
        block_kind="metric_paragraph",
        keywords=("下钻", "展开", "明细", "追到", "哪项", "哪个指标", "哪期", "具体"),
    ),
    "report": AnalysisPatternSpec(
        key="report",
        label="报告",
        description="将 Case、Claim、图表和章节组装为报告",
        task_type="report",
        block_kind="synthesis_paragraph",
        keywords=("报告", "生成报告", "出报告", "章节", "组装"),
    ),
    "overview": AnalysisPatternSpec(
        key="overview",
        label="综合概览",
        description="跨领域候选指标组合扫描",
        task_type="open_overview",
        block_kind="synthesis_paragraph",
        min_candidates=3,
        keywords=("综合", "概览", "画像", "体检", "重点", "值得分析", "看什么", "查什么"),
    ),
    "metric_lookup": AnalysisPatternSpec(
        key="metric_lookup",
        label="指标查询",
        description="单个确定指标的取值与口径",
        task_type="metric_lookup",
        block_kind="metric_paragraph",
        min_candidates=1,
    ),
    "comparison": AnalysisPatternSpec(
        key="comparison",
        label="对比",
        description="同比、环比、同行、目标、群体切片或个体之间",
        task_type="comparison",
        block_kind="comparison_paragraph",
        keywords=("对比", "比较", "相比", "差异", "差距"),
    ),
}


COMPARISON_BASIS: dict[str, tuple[str, tuple[str, ...]]] = {
    "yoy": ("同比", ("同比", "去年同期", "较上年")),
    "mom": ("环比", ("环比", "较上期", "上一期")),
    "peer": ("同行", ("同行", "同业", "同行业", "同类型")),
    "target": ("目标", ("目标", "计划", "预算", "考核线", "目标值")),
    "cohort_slice": ("群体切片", ("群体切片", "全库对比", "切片对比", "分组对比")),
    "entity_pair": ("个体之间", ("企业之间", "个体之间", "两家", "几家", "相互对比", "彼此对比")),
}


def detect_comparison_basis(query: str) -> str | None:
    text = (query or "").lower()
    for key, (_, markers) in COMPARISON_BASIS.items():
        if any(marker.lower() in text for marker in markers):
            return key
    return None


def detect_analysis_pattern(
    query: str,
    *,
    task_type: str | None = None,
    metric_count: int = 0,
) -> str:
    """Return one canonical pattern, preserving explicit Chinese intent."""
    text = (query or "").strip().lower()
    basis = detect_comparison_basis(query)
    ordered = (
        "scenario",
        "report",
        "attribution",
        "contribution",
        "correlation",
        "benchmark",
        "ranking",
        "anomaly",
        "trend",
        "stratification",
        "structure",
        "distribution",
        "drilldown",
        "overview",
    )
    components: list[str] = []
    for key in ordered:
        spec = ANALYSIS_PATTERNS[key]
        if spec.keywords and any(keyword.lower() in text for keyword in spec.keywords):
            components.append(key)
    if components:
        if len(components) == 1:
            if basis and components[0] not in {"benchmark", "comparison"}:
                return f"composite:comparison+{components[0]}"
            return components[0]
        # Data-specific combinations are first-class and remain inspectable.
        return "composite:" + "+".join(components[:3])
    if basis:
        return "comparison"
    if task_type in ANALYSIS_PATTERNS:
        return task_type
    if task_type == "open_overview":
        return "overview"
    if task_type == "diagnosis":
        return "anomaly"
    if task_type == "multi_metric" and metric_count >= 2:
        return "comparison"
    return "metric_lookup"


def pattern_metadata(
    query: str,
    *,
    task_type: str | None = None,
    metric_count: int = 0,
) -> dict[str, Any]:
    key = detect_analysis_pattern(query, task_type=task_type, metric_count=metric_count)
    spec = ANALYSIS_PATTERNS.get(key)
    components = key.removeprefix("composite:").split("+") if key.startswith("composite:") else [key]
    return {
        "analysis_pattern": key,
        "analysis_pattern_label": spec.label if spec else "复合分析",
        "analysis_pattern_description": spec.description if spec else "由多个基础分析模式派生",
        "analysis_components": components,
        "analysis_task_type": spec.task_type if spec else "distribution",
        "analysis_block_kind": spec.block_kind if spec else "comparison_paragraph",
        "comparison_basis": detect_comparison_basis(query),
        "requires_time": spec.requires_time if spec else False,
        "min_candidates": spec.min_candidates if spec else 2,
    }


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": spec.key,
            "label": spec.label,
            "description": spec.description,
            "task_type": spec.task_type,
            "block_kind": spec.block_kind,
            "requires_time": spec.requires_time,
            "min_candidates": spec.min_candidates,
        }
        for spec in ANALYSIS_PATTERNS.values()
    ]


def pattern_for_frame(frame: Any) -> str:
    return str(
        getattr(frame, "analysis_pattern", None)
        or detect_analysis_pattern(
            "",
            task_type=getattr(frame, "task_type", None),
            metric_count=len(getattr(frame, "metrics", []) or []),
        )
    )
