"""对话白话层：术语翻译、场景识别和提示词构造。

本模块不生成用户回答，也不提供固定模板兜底。
"""
from __future__ import annotations

import re
from typing import Literal

Scenario = Literal["loan", "rating", "warn", "audit", "general"]

# 内部术语 → 外行别名（长词优先替换）
TERM_ALIASES: list[tuple[str, str]] = [
    ("进销错配", "进货和销货对不上"),
    ("序列缺口", "开票号码断断续续"),
    ("六维雷达", "六方面经营体检"),
    ("六维评分", "六方面综合分"),
    ("税负率", "实际交税占营收的比例"),
    ("税负偏高", "该交的税明显偏高"),
    ("税负偏低", "该交的税明显偏低"),
    ("红字发票", "红冲发票（把已开发票冲掉）"),
    ("红冲", "发票冲红"),
    ("集中度", "买卖过于集中在少数对手"),
    ("Benford", "账面数字分布异常"),
    ("真实性交叉", "申报和开票对不上"),
    ("纳税信用", "税务信用"),
    ("流动比率", "短期能不能还上钱"),
    ("资产负债率", "欠债占家底的比例"),
]

def translate_terms(text: str) -> str:
    out = text or ""
    for src, dst in TERM_ALIASES:
        if src in out:
            out = out.replace(src, dst)
    return out


def detect_scenario(query: str | None) -> Scenario:
    q = (query or "").strip()
    if re.search(r"贷|授信|额度|放款|能不能借|批贷", q):
        return "loan"
    if re.search(r"评级|信用|纳税信用|几级|A\s*级|B\s*级", q):
        return "rating"
    if re.search(r"稽查|要查|可疑|核查|怎么查|重点查|查谁|账票|红冲", q):
        return "audit"
    if re.search(r"预警|异常|不对劲|风险在哪|哪里不对|哪里异常", q):
        return "warn"
    return "general"


def scenario_system_prompt(scenario: Scenario) -> str:
    focus = {
        "loan": "回答侧重「能不能贷/额度要不要收紧」，用外行听得懂的话。",
        "rating": "回答侧重「信用大概处在什么水平/为什么」，避免堆砌术语。",
        "warn": "回答侧重「哪里异常、为什么异常」，点出 1-2 个最关键信号。",
        "audit": "回答侧重「哪里可疑、该先查什么」，给可照做的核查动作。",
        "general": "先给好坏判断，再给数字，最后给一条可照做的建议。",
    }[scenario]
    return (
        "你是明鉴风控顾问。只能改写已给定结论的措辞，禁止新增任何数字或事实。"
        "输出 conclusions：若干句大白话——"
        "先给好坏/风险判断，再给来自给定结论的关键数字依据，最后给一条可照做的建议；"
        "句数不限，但每个数字必须能在给定结论中找到。"
        f"{focus}"
        "禁用「进销错配/序列缺口/六维雷达/税负」等内部词，改用「进货销货对不上/开票断断续续/六方面体检/该交的税占比」。"
    )
