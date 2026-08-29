"""AI 主导的定制报告对话引擎。

状态机：asking → propose →（确认）→ generate。
- asking：每轮只问一个问题，用 LLM 结构化输出同时推断已确定的槽位；
- propose：LLM 判定信息足够，产出 CustomReportSpec，展示方案 + 确认/调整追问；
- 无 LLM 时降级为规则问题梯（弃权优先，不编造方案）。

铁律：AI 只填充「结构（章节子集）+ 范围 + 标题 + 语气」槽位，不产生任何数字/事实。
"""
from __future__ import annotations

import re

from app.schemas.custom_report import CustomReportSpec
from app.services import llm_reply
from app.services.intent_engine import (
    _match_industry,
    _match_province,
    industry_l1_options,
    province_options,
)
from app.services.report_templates import (
    CUSTOM_CHAPTERS,
    CUSTOM_CHAPTER_DIMENSIONS,
    CUSTOM_CHAPTER_KEYWORDS,
    SCENARIOS,
    has_scenario_keyword,
    resolve_scenario,
    scope_label,
)

MAX_TURNS = 6

# propose 阶段的快捷追问按钮（走前端 followups，点击即发送对应文本）
PROPOSE_FOLLOWUPS = ["确认生成", "调整范围", "换个章节组合", "退出定制"]
ASKING_FOLLOWUPS = ["退出定制"]

_EXIT_RE = re.compile(r"^(退出(?:定制|报告)?|取消|不用了|算了|停止|不定制了|不要了)[。！？!?.，,]*$")
_CONFIRM_RE = re.compile(r"^(确认生成|确认|生成|就按这个|就这个|可以|好的|好|行|没问题|ok)[。！？!?.，,]*$", re.I)


def new_state() -> dict:
    return {
        "active": True,
        "stage": "asking",
        "turn": 0,
        "purpose": "",
        "spec": None,
        "last_question": "",
        "last_answer": "",
    }


def is_exit(q: str) -> bool:
    return bool(_EXIT_RE.match((q or "").strip()))


def is_confirm(q: str) -> bool:
    return bool(_CONFIRM_RE.match((q or "").strip()))


def normalize_spec(spec: CustomReportSpec | None) -> CustomReportSpec | None:
    """规则侧 clamp：chapters 去重并截断到词表内、industry/province 白名单外置 None。"""
    if spec is None:
        return None
    chapters: list[str] = []
    for c in spec.chapters or []:
        if c in CUSTOM_CHAPTERS and c not in chapters:
            chapters.append(c)
    industry = spec.industry_l1 if spec.industry_l1 in industry_l1_options() else None
    province = spec.province if spec.province in province_options() else None
    return CustomReportSpec(
        chapters=chapters,
        industry_l1=industry,
        province=province,
        title=(spec.title or "定制风控报告").strip() or "定制风控报告",
        tone=spec.tone,
        purpose=(spec.purpose or "").strip(),
    )


def spec_to_report_spec(spec: CustomReportSpec) -> dict:
    """把 CustomReportSpec 转成报告引擎可消费的 SCENARIOS 风格 spec dict。"""
    chapters = []
    for fn in spec.chapters:
        if fn not in CUSTOM_CHAPTERS:
            continue
        title, desc = CUSTOM_CHAPTERS[fn]
        chapters.append(
            {
                "function": fn,
                "dimension": CUSTOM_CHAPTER_DIMENSIONS.get(fn, "overall"),
                "title": title,
                "purpose": desc,
            }
        )
    return {
        "title": spec.title or "定制风控报告",
        "subtitle": "对话定制 · 自由组合章节",
        "tier": "general",
        "story": (spec.purpose or "根据用户诉求定制的风控报告。")[:200],
        "data_focus": ["财务数据", "税务数据", "发票数据", "企业基础信息"],
        "cover": {"motif": "compass", "accent": "#003366"},
        "kpis": [],
        "chapters": chapters,
    }


def proposal_text(spec: CustomReportSpec) -> str:
    """把方案摘要渲染成用户可见的确认文案。"""
    lines = [f"我判断你需要的是一份《{spec.title}》报告。"]
    scope = scope_label(spec.industry_l1, spec.province)
    if scope:
        lines.append(f"范围：{scope}")
    names = [CUSTOM_CHAPTERS[c][0] for c in spec.chapters if c in CUSTOM_CHAPTERS]
    lines.append(f"章节（按顺序）：{'、'.join(names) or '（未确定）'}")
    lines.append("确认无误请点「确认生成」；要调整请直接告诉我。")
    return "\n".join(lines)


def match_chapters(text: str) -> list[str]:
    """从文本识别章节，按用户提及的先后顺序返回（去重、白名单内）。

    数据驱动引导的核心：只认词表，不编造；识别不到返回空列表（弃权）。
    """
    tl = (text or "").lower()
    hits: list[tuple[int, str]] = []
    for kw, fn in CUSTOM_CHAPTER_KEYWORDS:
        idx = tl.find(kw.lower())
        if idx >= 0:
            hits.append((idx, fn))
    hits.sort(key=lambda x: x[0])
    seen: list[str] = []
    for _, fn in hits:
        if fn not in seen:
            seen.append(fn)
    return seen


def infer_title(chapters: list[str]) -> str:
    """按章节组合推导标题（纯结构，无数字/事实）。"""
    names = [CUSTOM_CHAPTERS[c][0] for c in chapters if c in CUSTOM_CHAPTERS]
    if not names:
        return "定制风控报告"
    if len(names) == 1:
        return f"{names[0]}风险报告"
    return f"{'与'.join(names)}风险报告"


def _spec_dict(state: dict) -> dict:
    """取累计槽位 dict（保持 CustomReportSpec 字段形状），无则新建。"""
    spec = state.get("spec")
    return dict(spec) if isinstance(spec, dict) else {}


def accumulate_slots(state: dict) -> None:
    """规则侧槽位累计（数据驱动）：从已累计诉求文本识别章节/行业/地区，合并进 state['spec']。

    只在白名单内匹配，不产生数字/事实；最大化覆盖用户已明确表达的信息，
    供 LLM 与「弃权兜底」复用，避免反复追问已回答过的槽位。
    """
    text = f"{state.get('purpose') or ''} {state.get('last_answer') or ''}".strip()
    spec = _spec_dict(state)

    chapters = list(spec.get("chapters") or [])
    for fn in match_chapters(text):
        if fn not in chapters:
            chapters.append(fn)
    if chapters:
        spec["chapters"] = chapters
    if not spec.get("industry_l1"):
        spec["industry_l1"] = _match_industry(text)
    if not spec.get("province"):
        spec["province"] = _match_province(text)
    spec["purpose"] = (state.get("purpose") or "").strip()
    if not spec.get("title") or spec.get("title") == "定制风控报告":
        spec["title"] = infer_title(chapters)
    state["spec"] = spec


def _spec_from_slots(state: dict) -> CustomReportSpec | None:
    """把累计槽位转成可提案的 spec；识别不到章节则弃权返回 None。

    章节识别优先走自由组合词表；若用户说的是场景名（尽调/画像/总览等），
    回退到该固定场景的章节子集，保证「最大化覆盖」而非直接弃权。
    """
    text = f"{state.get('purpose') or ''} {state.get('last_answer') or ''}".strip()
    chapters = match_chapters(text)
    if not chapters and has_scenario_keyword(text):
        chapters = [ch["function"] for ch in SCENARIOS[resolve_scenario(text)]["chapters"]]
    if not chapters:
        return None
    spec = _spec_dict(state)
    industry = spec.get("industry_l1") or _match_industry(text)
    province = spec.get("province") or _match_province(text)
    title = spec.get("title") or ""
    if not title or title == "定制风控报告":
        title = infer_title(chapters)
    return CustomReportSpec(
        chapters=chapters,
        industry_l1=industry if industry in industry_l1_options() else None,
        province=province if province in province_options() else None,
        title=title,
        tone=spec.get("tone"),
        purpose=(spec.get("purpose") or "").strip(),
    )


def _merge_llm_spec(state: dict, spec) -> None:
    """LLM 未 propose 但给了部分 spec 时，合并进累计槽位（LLM 为准，规则补漏）。"""
    if spec is None:
        return
    acc = _spec_dict(state)
    chapters = list(acc.get("chapters") or [])
    for c in spec.chapters or []:
        if c in CUSTOM_CHAPTERS and c not in chapters:
            chapters.append(c)
    if chapters:
        acc["chapters"] = chapters
    if spec.industry_l1 in industry_l1_options():
        acc["industry_l1"] = spec.industry_l1
    if spec.province in province_options():
        acc["province"] = spec.province
    if spec.purpose:
        acc["purpose"] = spec.purpose
    state["spec"] = acc


def _merge_with_slots(spec: CustomReportSpec, state: dict) -> CustomReportSpec:
    """LLM 方案与规则累计槽位合并：LLM 为准，规则补漏遗漏的章节/范围（最大化覆盖）。"""
    acc = _spec_dict(state)
    chapters = list(spec.chapters or [])
    for c in acc.get("chapters") or []:
        if c in CUSTOM_CHAPTERS and c not in chapters:
            chapters.append(c)
    industry = spec.industry_l1 or acc.get("industry_l1")
    province = spec.province or acc.get("province")
    title = spec.title if (spec.title and spec.title != "定制风控报告") else infer_title(chapters)
    return CustomReportSpec(
        chapters=chapters,
        industry_l1=industry if industry in industry_l1_options() else None,
        province=province if province in province_options() else None,
        title=title,
        tone=spec.tone,
        purpose=(spec.purpose or acc.get("purpose") or "").strip(),
    )


def _salvage_or_give_up(state: dict) -> dict:
    """轮次耗尽/无法精判时：能用已识别槽位成方案就成方案（最大化覆盖），否则才弃权退回固定场景。"""
    spec = _spec_from_slots(state)
    if spec is not None:
        # 章节可能已新增（如用户在 LLM 方案后又补了「财务健康」），标题按最终章节重推，
        # 避免沿用 LLM 早期标题导致「标题说营收趋势、章节却含财务健康」的脱节。
        spec = CustomReportSpec(
            chapters=spec.chapters,
            industry_l1=spec.industry_l1,
            province=spec.province,
            title=infer_title(spec.chapters),
            tone=spec.tone,
            purpose=spec.purpose,
        )
        state["spec"] = spec.model_dump()
        return {
            "reply": "我已按你提到的关注点整理了方案（章节与范围见下）。若需调整可直接说明，或点「确认生成」直接出报告。\n\n" + proposal_text(spec),
            "followups": PROPOSE_FOLLOWUPS,
            "stage": "propose",
            "spec": spec,
            "meta": {"custom_proposal": spec.model_dump(), "salvaged": True},
            "llm": False,
        }
    from app.services.report_templates import scenario_path_prompts

    return {
        "reply": "多轮对话后我仍无法准确判断你的定制需求。为避免误导，建议改用固定模板，或重新开始定制。",
        "followups": scenario_path_prompts(),
        "stage": "asking",
        "spec": None,
        "meta": {"actions": [{"label": "打开报告生成向导", "target": "/report?wizard=1"}]},
        "llm": False,
    }


def rule_next_question(state: dict) -> str:
    """无 LLM 时的确定性问题梯。"""
    turn = int(state.get("turn") or 0)
    if turn <= 1:
        return "请告诉我这份报告主要想解决什么风险？比如财务健康、税务合规、发票舞弊、综合尽调、企业画像或总览。"
    return "还需要限定行业或地区范围吗？例如「制造业」或「广东」；不需要就说「全部样本」。"


def rule_turn(state: dict, answer: str) -> dict:
    """无 LLM 降级：规则把已识别槽位转成方案（章节自由组合 + 范围）；识别不到则弃权给固定场景快捷。"""
    spec = _spec_from_slots(state)
    if spec is not None:
        state["spec"] = spec.model_dump()
        return {
            "reply": proposal_text(spec),
            "followups": PROPOSE_FOLLOWUPS,
            "stage": "propose",
            "spec": spec,
            "meta": {"custom_proposal": spec.model_dump()},
            "llm": False,
        }
    # 仍未识别到章节 → 给出固定场景快捷（走 followups）
    return {
        "reply": "我这边暂时无法自动判断场景，请从以下选择一个，或直接说关键词（财务/税务/发票舞弊/尽调/画像/总览）：",
        "followups": [SCENARIOS[k]["title"] for k in ("financial", "tax", "fraud", "due_diligence", "profile", "overview")],
        "stage": "asking",
        "spec": None,
        "meta": {},
        "llm": False,
    }


async def next_turn(state: dict, answer: str) -> dict:
    """推进一轮 asking。返回 {reply, followups, stage, spec, meta, llm}。"""
    state["turn"] = int(state.get("turn") or 0) + 1
    state["last_answer"] = (answer or "").strip()
    if state["last_answer"]:
        purpose = (state.get("purpose") or "").strip()
        state["purpose"] = f"{purpose} {state['last_answer']}".strip()

    # 规则侧槽位累计（数据驱动）：每轮先把已明确信息合并进 state['spec']
    accumulate_slots(state)

    # 轮次耗尽：弃权优先，但先最大化覆盖——能用已识别槽位成方案就成方案，否则才退回固定场景
    if state["turn"] > MAX_TURNS:
        return _salvage_or_give_up(state)

    turn = await llm_reply.llm_custom_report_turn(state)
    if turn is None:
        return rule_turn(state, answer)

    if turn.propose and turn.spec is not None and turn.spec.chapters:
        spec = _merge_with_slots(normalize_spec(turn.spec), state)
        state["spec"] = spec.model_dump()
        return {
            "reply": proposal_text(spec),
            "followups": PROPOSE_FOLLOWUPS,
            "stage": "propose",
            "spec": spec,
            "meta": {"custom_proposal": spec.model_dump()},
            "llm": True,
        }

    # 未 propose：LLM 若给了部分 spec 则合并进累计（否则保留规则侧已识别槽位）
    _merge_llm_spec(state, turn.spec)

    q = (turn.next_question or "").strip() or rule_next_question(state)
    state["last_question"] = q
    return {
        "reply": q,
        "followups": ASKING_FOLLOWUPS,
        "stage": "asking",
        "spec": None,
        "meta": {},
        "llm": True,
    }
