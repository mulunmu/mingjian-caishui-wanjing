"""报告 claim schema — LLM 只组织语言，数字必须来自 computed 结论"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Confidence = Literal["computed", "inferred", "asserted"]


class ClaimValue(BaseModel):
    metric: str
    number: float | int | None = None
    unit: str = ""


class ClaimTrace(BaseModel):
    table: str
    field: str
    detail_table: str | None = None
    query_id: str | None = None


class Claim(BaseModel):
    claim: str = Field(..., description="结论句，数字必须来自 value")
    value: ClaimValue | None = None
    trace: ClaimTrace | None = None
    confidence: Confidence = "computed"
    evidence_chain: list[str] = Field(default_factory=list)


class ClaimBundle(BaseModel):
    """LLM 结构化输出：仅改写已有结论，禁止新增数字"""

    conclusions: list[str] = Field(default_factory=list, description="面向用户的结论句")
    followups: list[str] = Field(default_factory=list, description="追问建议")
    report_hint: str | None = Field(default=None, description="覆盖度够时的报告提示")


def filter_claims(claims: list[Claim]) -> list[Claim]:
    """asserted（LLM 自由发挥）丢弃；inferred 保留但标记。"""
    return [c for c in claims if c.confidence in ("computed", "inferred")]


def claims_to_public_reply(claims: list[Claim], followups: list[str] | None = None) -> str:
    """对话层：只渲染结论 + 追问，隐藏证据链。"""
    kept = filter_claims(claims)
    lines = [c.claim for c in kept if c.claim]
    text = "\n".join(lines) if lines else "暂无可用结论。"
    if followups:
        text += "\n\n可继续追问：" + "；".join(followups[:3])
    return text


def claims_to_dict(claims: list[Claim]) -> list[dict[str, Any]]:
    return [c.model_dump() for c in filter_claims(claims)]
