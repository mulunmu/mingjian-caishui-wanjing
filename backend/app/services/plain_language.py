"""对话白话层（M3）：术语翻译 + 四场景顾问结构。

铁律：数字只来自 claims，本模块只改表达、不编数字。
输出结构：一句话大白话结论 → 1-2 个关键数字 → 一条能照做的建议。
"""
from __future__ import annotations

import re
from typing import Literal

from app.schemas.claim import Claim, ClaimValue, filter_claims

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

_RISK_HINTS = ("偏弱", "预警", "高风险", "异常", "可疑", "承压", "越线", "偏低", "偏高", "错配", "缺口", "不连续")
_GOOD_HINTS = ("稳健", "达标", "良好", "正常", "偏低风险", "低风险", "A级", "A 级")


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


def _claim_tone(claims: list[Claim]) -> Literal["good", "mixed", "bad", "unknown"]:
    text = " ".join((c.claim or "") for c in claims)
    has_bad = any(h in text for h in _RISK_HINTS)
    has_good = any(h in text for h in _GOOD_HINTS)
    if has_bad and has_good:
        return "mixed"
    if has_bad:
        return "bad"
    if has_good:
        return "good"
    return "unknown"


def _fmt_number(v: ClaimValue) -> str:
    n = v.number
    if n is None:
        return ""
    if isinstance(n, float) and not n.is_integer():
        num = f"{n:.2f}".rstrip("0").rstrip(".")
    else:
        num = str(int(n) if isinstance(n, float) and n.is_integer() else n)
    unit = (v.unit or "").strip()
    return f"{num}{unit}"


def _pick_number_lines(claims: list[Claim], limit: int = 2) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for c in claims:
        if not c.value or c.value.number is None:
            continue
        key = f"{c.value.metric}:{c.value.number}:{c.value.unit}"
        if key in seen:
            continue
        seen.add(key)
        num = _fmt_number(c.value)
        label = translate_terms((c.claim or "").strip())
        # 压缩成「标签 + 数字」短句，避免整段复读
        short = re.split(r"[，。；]", label)[0].strip() or (c.value.metric or "关键指标")
        if num and num not in short:
            lines.append(f"关键数字：{short}为 {num}。")
        else:
            lines.append(f"关键数字：{short}。")
        if len(lines) >= limit:
            break
    return lines


def _headline(scenario: Scenario, tone: str, claims: list[Claim]) -> str:
    first = translate_terms((claims[0].claim if claims else "") or "").strip()
    first = re.split(r"[。！？]", first)[0].strip()
    if scenario == "loan":
        if tone == "good":
            return f"从现有财税票信号看，放贷风险整体可控；{first or '经营面偏稳'}。"
        if tone == "bad":
            return f"从现有信号看，现阶段放贷需谨慎，不宜贸然放行；{first or '主要风险点已显现'}。"
        if tone == "mixed":
            return f"能不能贷要看额度与担保：有稳健面，也有明确风险点；{first or '建议先压降敞口'}。"
        return f"放贷决策需结合下述关键数字；{first or '暂无足够结论，请先补问经营或发票信号'}。"
    if scenario == "rating":
        if tone == "good":
            return f"信用画像偏稳；{first or '等级信号总体正向'}。"
        if tone == "bad":
            return f"信用画像偏弱，等级承压；{first or '扣分/预警信号更突出'}。"
        return f"信用等级要看扣分项与经营一致性；{first or '请结合关键数字判断'}。"
    if scenario == "warn":
        if tone == "bad":
            return f"异常主要集中在经营/发票侧；{first or '已出现需盯住的信号'}。"
        if tone == "good":
            return f"当前未见突出异常，整体偏平稳；{first or '可继续抽查薄弱项'}。"
        return f"有几处需要盯住的异常信号；{first or '建议先看发票与交税是否对得上'}。"
    if scenario == "audit":
        if tone == "bad":
            return f"更值得优先核查的是异常开票与账票不一致处；{first or '建议按信号下钻'}。"
        return f"稽查视角下先锁定可疑点再下钻；{first or '优先看冲红、错配与申报差异'}。"
    # general
    if tone == "good":
        return f"整体偏稳；{first or '关键指标未见明显越线'}。"
    if tone == "bad":
        return f"整体偏弱，风险更集中；{first or '建议先处理最高信号'}。"
    if tone == "mixed":
        return f"有好有坏：稳健项与风险项并存；{first or '先抓住最弱一环'}。"
    return f"{first or '已完成核验，请继续追问具体场景（放贷/评级/预警/稽查）。'}。"


def _advice(scenario: Scenario, tone: str, claims: list[Claim]) -> str:
    blob = " ".join(translate_terms(c.claim or "") for c in claims)
    if scenario == "loan":
        if tone == "bad":
            return "建议：先核查异常发票与进销是否对得上，再决定是否压降额度或增加担保。"
        return "建议：按行业均值设额度上限，并把发票连续性、交税是否对得上作为放贷附加条件。"
    if scenario == "rating":
        return "建议：对照官方扣分项核对「冲红次数/申报差异」等可解释因子，再确认等级口径。"
    if scenario == "warn":
        if "对不上" in blob or "冲红" in blob or "断断续续" in blob:
            return "建议：导出近期红冲与进销明细，按对手方名单逐笔核对。"
        return "建议：把最高信号企业/行业拉出来，核对近 3 个月开票与申报是否同向。"
    if scenario == "audit":
        return "建议：优先抽查红冲发票对应销售方名单，并核对申报收入与开票收入是否一致。"
    if tone == "bad":
        return "建议：先处理最高风险信号，再回头看综合分是否回升。"
    return "建议：用「行业对比 + 单户下钻」确认结论是否稳定，需要报告时可直接说出场景。"


def build_advisor_reply(
    claims: list[Claim],
    *,
    query: str | None = None,
    followups: list[str] | None = None,
    report_hint: str | None = None,
) -> str:
    """模板/降级路径的顾问式回复（数字仍只来自 claims）。"""
    kept = filter_claims(claims)
    scenario = detect_scenario(query)
    tone = _claim_tone(kept)
    parts: list[str] = [_headline(scenario, tone, kept)]
    parts.extend(_pick_number_lines(kept, limit=2))
    parts.append(_advice(scenario, tone, kept))
    if report_hint:
        parts.append(translate_terms(report_hint.strip()))
    text = "\n".join(p for p in parts if p)
    if followups:
        # 追问只走结构化 chips，禁止正文「A；B；C」拼句被整段重发
        text += "\n\n（下方按钮可继续追问）"
    return text.strip() or "分析完成，请换个场景继续问（例如：这家能贷吗？）。"


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
