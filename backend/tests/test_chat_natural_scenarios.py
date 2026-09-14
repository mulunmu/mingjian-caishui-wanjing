"""M3：对话自然化 — 百级场景验证（模板路径，确定性）。

覆盖：放贷 / 评级 / 预警 / 稽查 / 综合 × 多行业 × 好坏语气 × 术语翻译。
硬指标：无机器前缀；首句外行能读懂好坏；含建议；数字来自 claim。
"""
from __future__ import annotations

import itertools
import re
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.claim import Claim, ClaimValue
from app.services.llm_reply import _template_from_claims, TEMPLATE_PREFIX
from app.services.plain_language import (
    TERM_ALIASES,
    build_advisor_reply,
    detect_scenario,
    translate_terms,
)

INDUSTRIES = ["制造", "批发零售", "建筑", "IT软件", "服务", "其他"]
REGIONS = ["广东", "浙江", "江苏", "北京", "上海", "四川"]
TONES = {
    "good": ("经营稳健，纳税信用偏向 A 级。", 85.0, "分"),
    "bad": ("进销错配偏高，序列缺口明显，税负偏低。", 42.0, "分"),
    "mixed": ("综合评分中等，红字发票偏多但营收同比尚可。", 61.5, "分"),
}

LOAN_QS = [
    "这家企业能不能贷？",
    "可以给多少授信额度？",
    "放贷风险大不大？",
    "批贷前还要看什么？",
    "值不值得放款？",
]
RATING_QS = [
    "纳税信用大概什么等级？",
    "信用怎么样？",
    "评级依据是什么？",
    "为什么不是 A 级？",
    "信用画像稳不稳？",
]
WARN_QS = [
    "哪里不对劲？",
    "哪里异常？",
    "主要预警是什么？",
    "风险在哪？",
    "最近有什么异常信号？",
]
AUDIT_QS = [
    "哪里可疑要查？",
    "稽查优先查什么？",
    "该核查谁？",
    "红冲要不要重点查？",
    "账票不一致怎么查？",
]
GENERAL_QS = [
    "整体风险评分如何？",
    "经营真实性怎么样？",
    "行业趋势如何？",
    "和同业比怎么样？",
    "先给我一句结论。",
]

SCENARIO_QUERIES = {
    "loan": LOAN_QS,
    "rating": RATING_QS,
    "warn": WARN_QS,
    "audit": AUDIT_QS,
    "general": GENERAL_QS,
}

_VERDICT_RE = re.compile(
    r"稳|弱|好|坏|风险|异常|可疑|谨慎|可控|承压|偏弱|偏稳|达标|预警|放贷|信用|核查|对不上"
)
_JARGON = ("进销错配", "序列缺口", "六维雷达", "税负率")


def _claim(tone: str, industry: str) -> list[Claim]:
    text, num, unit = TONES[tone]
    return [
        Claim(
            claim=f"{industry}样本：{text}",
            value=ClaimValue(metric="overall_score", number=num, unit=unit),
            confidence="computed",
        ),
        Claim(
            claim="近 3 个月红字发票占比偏高。" if tone != "good" else "近 3 个月开票连续，未见明显冲红异常。",
            value=ClaimValue(metric="red_ratio", number=12.5 if tone != "good" else 1.2, unit="%"),
            confidence="computed",
        ),
    ]


def _build_cases() -> list[tuple]:
    cases: list[tuple] = []
    for scenario, queries in SCENARIO_QUERIES.items():
        for q, tone, industry in itertools.product(queries, TONES.keys(), INDUSTRIES):
            cases.append((scenario, q, tone, industry))
    # 地区追问变体，补足到 >= 100（上面已远超）
    for region, tone in itertools.product(REGIONS, TONES.keys()):
        cases.append(("warn", f"{region}哪里异常？", tone, "制造"))
    return cases


CASES = _build_cases()


def test_case_count_at_least_100():
    assert len(CASES) >= 100, f"got {len(CASES)}"


@pytest.mark.parametrize("scenario,query,tone,industry", CASES)
def test_advisor_reply_natural_multi_scenario(scenario, query, tone, industry):
    claims = _claim(tone, industry)
    reply = build_advisor_reply(claims, query=query, followups=["继续问", "出报告"])

    assert "[规则模板生成]" not in reply
    assert TEMPLATE_PREFIX == "" or not reply.startswith("[规则模板生成]")

    first = reply.split("\n", 1)[0]
    assert _VERDICT_RE.search(first), f"首句不可读: {first!r} | q={query}"

    assert "建议" in reply, f"缺少可照做建议: {reply[:120]!r}"

    # 数字必须来自 claim
    assert "85" in reply or "42" in reply or "61.5" in reply or "12.5" in reply or "1.2" in reply

    # 内部术语应被翻译掉（允许出现在替换后的白话里，不允许原词残留）
    for j in _JARGON:
        assert j not in reply, f"术语未翻译 {j}: {reply}"

    detected = detect_scenario(query)
    assert detected == scenario, f"场景识别失败: {query!r} -> {detected}, want {scenario}"


@pytest.mark.parametrize("scenario,query,tone,industry", CASES[:40])
def test_template_from_claims_matches_advisor(scenario, query, tone, industry):
    claims = _claim(tone, industry)
    reply = _template_from_claims(claims, ["追问"], query=query)
    assert "[规则模板生成]" not in reply
    assert "建议" in reply
    assert _VERDICT_RE.search(reply.split("\n", 1)[0])


def test_term_aliases_cover_core_jargon():
    srcs = {a[0] for a in TERM_ALIASES}
    for j in _JARGON:
        assert j in srcs
    sample = "存在进销错配与序列缺口，六维雷达显示税负率偏低。"
    out = translate_terms(sample)
    for j in _JARGON:
        assert j not in out


def test_four_scenario_headlines_differ():
    claims = _claim("bad", "制造")
    replies = {
        s: build_advisor_reply(claims, query=qs[0])
        for s, qs in SCENARIO_QUERIES.items()
        if s != "general"
    }
    # 四场景首句应体现各自侧重点
    assert "贷" in replies["loan"] or "放贷" in replies["loan"] or "谨慎" in replies["loan"]
    assert "信用" in replies["rating"] or "等级" in replies["rating"]
    assert "异常" in replies["warn"] or "信号" in replies["warn"]
    assert "核查" in replies["audit"] or "稽查" in replies["audit"] or "可疑" in replies["audit"]


def test_scenario_detector_matrix():
    assert detect_scenario("这家能贷吗") == "loan"
    assert detect_scenario("纳税信用等级") == "rating"
    assert detect_scenario("哪里不对劲") == "warn"
    assert detect_scenario("哪里可疑要查") == "audit"
    assert detect_scenario("整体评分") == "general"
