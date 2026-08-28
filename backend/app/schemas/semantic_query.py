"""SemanticQuery 中间表示：NL 理解与执行之间的结构化 IR。

借鉴 SuperSonic 的 SchemaMapper→Parser→Corrector→Translator：LLM 负责把自然语言
解析成带槽位的语义查询，规则层只做校正与兜底；执行层按 query_type 分派到各
build_*_claims builder。数字仍由算法产出，LLM 不改数字。
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class QueryType(str, Enum):
    lookup = "lookup"              # 单一指标取值（某切片平均信用分是多少）
    aggregation = "aggregation"    # 汇总（均值/计数），可能带 group_by
    comparison = "comparison"      # A 与 B 对比（广东 vs 江苏 / 制造 vs 服务）
    trend = "trend"                # 时间序列走向（营收同比）
    ranking = "ranking"            # 前 N / 后 N
    distribution = "distribution"  # 分布（风险等级/信用分桶/信号桶）
    segmentation = "segmentation"  # 按维度拆分某指标（按行业拆真实性）
    correlation = "correlation"    # 两指标相关性
    faq = "faq"                    # 产品/使用问题
    methodology = "methodology"    # 口径/算法如何计算


class SortSpec(BaseModel):
    metric: str = ""                     # canonical metric_key
    order: Literal["asc", "desc"] = "desc"


class TimeRange(BaseModel):
    # 数据为时点快照，P0 仅占位，不强约束
    granularity: Literal["month", "quarter", "year"] = "year"


class CompareTarget(BaseModel):
    dimension: str = "province"          # industry_l1 | province | scale_label
    values: list[str] = Field(default_factory=list)


class SemanticQuery(BaseModel):
    query_type: QueryType = QueryType.aggregation
    metrics: list[str] = Field(default_factory=list)          # canonical / runtime metric keys
    dimensions: list[str] = Field(default_factory=list)       # group_by 维度
    filters: dict[str, list[str]] = Field(default_factory=dict)  # {industry_l1:["制造"], province:["广东"]}
    compare: list[CompareTarget] = Field(default_factory=list)
    sort: SortSpec | None = None
    limit: int | None = None
    time_range: TimeRange | None = None
    entities: list[str] = Field(default_factory=list)         # 仅 ENT\d+ 匿名 id，绝不含具名企业
    raw_query: str = ""
    confidence: float = 0.6
    source: Literal["rule", "llm", "corrected"] = "rule"
    followup: bool = False
