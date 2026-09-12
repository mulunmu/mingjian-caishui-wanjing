"""定制报告对话：LLM 结构化输出的槽位 schema。

AI 只填充「结构（章节子集）+ 范围 + 标题 + 语气」，不产生任何数字/事实（铁律）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CustomReportSpec(BaseModel):
    """一份定制报告的完整方案：8 个可组合功能的有序子集 + 范围 + 标题。"""

    chapters: list[str] = Field(default_factory=list)  # CUSTOM_CHAPTERS 的有序子集
    industry_l1: str | None = None
    province: str | None = None
    enterprises: list[str] = Field(default_factory=list)  # 指定企业（「企业N」可读名或企业 id）
    title: str = "定制风控报告"
    tone: str | None = None  # 语气提示（可选，未用则回退 custom 语气）
    purpose: str = ""  # 用户诉求的原文摘要


class CustomReportTurn(BaseModel):
    """单轮对话的 LLM 返回：要么继续问，要么给出方案。"""

    next_question: str | None = None  # 信息不足 → 下一个要问的单个简短问题
    propose: bool = False  # 信息足够 → 产出 spec
    spec: CustomReportSpec | None = None
