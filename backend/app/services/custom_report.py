"""AI 主导的定制报告对话引擎。

状态机：asking → propose →（确认）→ generate。
- asking：每轮只问一个问题，用 LLM 结构化输出同时推断已确定的槽位；
- propose：LLM 判定信息足够，产出 CustomReportSpec，展示方案 + 确认/调整追问；
- 无 LLM 时降级为规则问题梯（弃权优先，不编造方案）。

铁律：AI 只填充「结构（章节子集）+ 范围 + 标题 + 语气」槽位，不产生任何数字/事实。
"""
from __future__ import annotations

import re
from typing import Any

from app.schemas.custom_report import CustomReportSpec
from app.services import llm_reply
from app.services.intent_engine import (
    _match_industry,
    _match_province,
    industry_l1_options,
    province_options,
)
from app.services.report_templates import (
    CHAPTER_REGISTRY,
    CUSTOM_CHAPTERS,
    CUSTOM_CHAPTER_DIMENSIONS,
    CUSTOM_CHAPTER_KEYWORDS,
    has_scenario_keyword,
    sanitize_surface_industry_terms,
    scope_label,
)

MAX_TURNS = 6

# propose 阶段的快捷追问按钮（走前端 followups，点击即发送对应文本）
PROPOSE_FOLLOWUPS = ["确认生成", "调整范围", "换个章节组合", "退出定制"]
ASKING_FOLLOWUPS = ["退出定制"]

# 定制对话场景预设：根据用户话术识别「场景意图」→ 章节子集（本意：对话定报告，不是砍成两主题）
# 与向导快捷模板（portrait/alert）分离：向导去冗杂；定制仍可财务/税务/发票/尽调/画像/预警。
CUSTOM_SCENE_PRESETS: dict[str, list[str]] = {
    "financial": ["financial", "authenticity", "benchmark", "trend"],
    "tax": ["tax", "signal", "authenticity"],
    "fraud": ["fraud", "authenticity", "signal"],
    "due_diligence": ["score", "authenticity", "fraud", "benchmark", "signal"],
    "profile": ["score", "trend", "benchmark", "signal"],
    "overview": ["score", "signal", "financial", "tax", "fraud", "authenticity"],
    "portrait": ["score", "trend", "benchmark"],
    "alert": ["signal", "fraud", "tax", "authenticity"],
}

# 定制专用别名（不走向导的 portrait/alert 归一，避免「财务」被吞成预警）
_CUSTOM_SCENE_ALIASES: list[tuple[str, str]] = [
    ("综合总览", "overview"),
    ("样本库画像", "portrait"),
    ("风险预警", "alert"),
    ("财务健康", "financial"),
    ("企业画像", "profile"),
    ("发票舞弊", "fraud"),
    ("税务合规", "tax"),
    ("综合尽调", "due_diligence"),
    ("全面体检", "due_diligence"),
    ("基本面", "financial"),
    ("画像", "portrait"),
    ("预警", "alert"),
    ("总览", "overview"),
    ("尽调", "due_diligence"),
    ("财务", "financial"),
    ("税务", "tax"),
    ("发票", "fraud"),
    ("舞弊", "fraud"),
    ("欺诈", "fraud"),
]

_EXIT_RE = re.compile(r"^(退出(?:定制|报告)?|取消|不用了|算了|停止|不定制了|不要了)[。！？!?.，,]*$")
_CONFIRM_RE = re.compile(r"^(确认生成|确认|生成|就按这个|就这个|可以|好的|好|行|没问题|ok)[。！？!?.，,]*$", re.I)
_ENTERPRISE_RE = re.compile(r"企业\s*\d+")


def _dedupe_enterprises(items: list[str] | None) -> list[str]:
    """企业槽位去重 + 去空（企业 id 解析在生成时做，这里只保可读名/原始串）。"""
    out: list[str] = []
    for it in items or []:
        s = (it or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def match_enterprises(text: str) -> list[str]:
    """从文本提取显式「企业N」可读名（区间/「全部样本」等不视为指定企业，返回空）。"""
    return _dedupe_enterprises(_ENTERPRISE_RE.findall(text or ""))


def new_state() -> dict:
    return {
        "active": True,
        "stage": "asking",
        "turn": 0,
        "purpose": "",
        "spec": None,
        "last_question": "",
        "last_answer": "",
        # 范围：enterprise | industry | all | ""（未定）
        "scope_mode": "",
    }


def detect_scope_mode(text: str, state: dict | None = None) -> str:
    """从用户话术识别范围模式（个体 / 行业 / 全库）。"""
    t = text or ""
    st = state or {}
    spec = st.get("spec") if isinstance(st.get("spec"), dict) else {}
    if match_enterprises(t) or (spec or {}).get("enterprises"):
        return "enterprise"
    if "全部样本" in t or "全库" in t or "全量" in t or "所有企业" in t:
        return "all"
    if "指定企业" in t or "单户" in t or "个体体检" in t or "企业体检" in t:
        return "enterprise"
    if _match_industry(t) or (spec or {}).get("industry_l1") or "行业" in t:
        return "industry"
    prev = (st.get("scope_mode") or "").strip()
    return prev


def clamp_chapters_for_scope(chapters: list[str], scope_mode: str = "") -> list[str]:
    """定制本意：章节只按 CUSTOM_CHAPTERS 白名单规范化；范围只滤数据，不砍场景积木。

    scope_mode 保留参数以兼容调用方，不再把全库/行业夹成「画像+预警」两积木。
    """
    _ = scope_mode
    out: list[str] = []
    for c in chapters or []:
        if c in CHAPTER_REGISTRY and c not in out:
            out.append(c)
    return out


def resolve_custom_scene(text: str) -> str | None:
    """从用户话术识别定制场景意图（财务/税务/…），供章节预设展开。"""
    t = text or ""
    for kw, key in sorted(_CUSTOM_SCENE_ALIASES, key=lambda kv: len(kv[0]), reverse=True):
        if kw in t:
            return key
    return None


def chapters_from_custom_scene(text: str) -> list[str]:
    """场景关键词 → 预设章节；无命中返回空（弃权，不编造）。"""
    key = resolve_custom_scene(text)
    if not key:
        return []
    return list(CUSTOM_SCENE_PRESETS.get(key) or [])


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
        if c in CHAPTER_REGISTRY and c not in chapters:
            chapters.append(c)
    industry = spec.industry_l1 if spec.industry_l1 in industry_l1_options() else None
    province = spec.province if spec.province in province_options() else None
    enterprises = _dedupe_enterprises(spec.enterprises)
    return CustomReportSpec(
        chapters=chapters,
        industry_l1=industry,
        province=province,
        enterprises=enterprises,
        title=sanitize_surface_industry_terms(
            (spec.title or "定制风控报告").strip() or "定制风控报告"
        ),
        tone=spec.tone,
        purpose=(spec.purpose or "").strip(),
    )


def spec_to_report_spec(spec: CustomReportSpec) -> dict:
    """把 CustomReportSpec 转成报告引擎可消费的 SCENARIOS 风格 spec dict。"""
    chapters = []
    for fn in spec.chapters:
        if fn not in CHAPTER_REGISTRY:
            continue
        title = CHAPTER_REGISTRY[fn]["title"]
        desc = CHAPTER_REGISTRY[fn]["desc"]
        chapters.append(
            {
                "function": fn,
                "dimension": (CHAPTER_REGISTRY.get(fn) or {}).get("default_dimension", "overall"),
                "title": title,
                "purpose": desc,
            }
        )
    # 单章定制：给场景专属 KPI，避免退回通用「高风险/标记·项」歧义卡
    kpis: list[dict[str, Any]] = []
    ch_set = set(spec.chapters or [])
    if ch_set == {"fraud"} or (len(ch_set) == 1 and "fraud" in ch_set):
        kpis = [
            {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
            {"label": "舞弊预警主体数", "metric": "flagged_count", "unit": "家", "source": "fraud"},
            {"label": "舞弊信号", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
        ]
    return {
        "title": spec.title or "定制风控报告",
        "subtitle": "对话定制 · 自由组合章节",
        "tier": "general",
        # story 不在此写死：由 _build_context_from_spec → compose_story_from_chapters 从 claim 拼装
        "story": "",
        "purpose": (spec.purpose or "").strip(),
        "governing_question": (spec.purpose or "").strip() or None,
        "data_focus": ["财务数据", "税务数据", "发票数据", "企业基础信息"],
        "cover": {"motif": "compass", "accent": "#152446"},
        "kpis": kpis,
        "chapters": chapters,
    }


def proposal_text(spec: CustomReportSpec) -> str:
    """把方案摘要渲染成用户可见的确认文案。"""
    lines = [f"我根据对话判断，你需要的是一份《{spec.title}》报告。"]
    scope = scope_label(spec.industry_l1, spec.province)
    if spec.enterprises:
        scope = ("、".join(spec.enterprises)) if not scope else f"{scope} · 指定企业 {'、'.join(spec.enterprises)}"
        lines.append(f"数据范围：{scope}")
    elif scope:
        lines.append(f"数据范围：{scope}（行业切片）")
    else:
        lines.append("数据范围：全部样本（未限定行业/企业）")
    names = [CHAPTER_REGISTRY[c]["title"] for c in spec.chapters if c in CHAPTER_REGISTRY]
    lines.append(f"章节（按对话识别，可调整）：{'、'.join(names) or '（未确定）'}")
    lines.append("确认无误请点「确认生成」；要换场景或章节请直接说明。")
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
    names = [CHAPTER_REGISTRY[c]["title"] for c in chapters if c in CHAPTER_REGISTRY]
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
    """规则侧槽位累计：识别章节/场景/行业/地区；章节不因范围被砍。"""
    text = f"{state.get('purpose') or ''} {state.get('last_answer') or ''}".strip()
    state["scope_mode"] = detect_scope_mode(text, state)
    spec = _spec_dict(state)

    chapters = list(spec.get("chapters") or [])
    for fn in match_chapters(text):
        if fn not in chapters:
            chapters.append(fn)
    if not chapters:
        chapters = chapters_from_custom_scene(text)
    chapters = clamp_chapters_for_scope(chapters, state.get("scope_mode") or "")
    if chapters:
        spec["chapters"] = chapters
    if not spec.get("industry_l1"):
        spec["industry_l1"] = _match_industry(text)
    if not spec.get("province"):
        spec["province"] = _match_province(text)
    ent = match_enterprises(text)
    if ent:
        existing = _dedupe_enterprises(spec.get("enterprises") or [])
        spec["enterprises"] = _dedupe_enterprises(existing + ent)
        state["scope_mode"] = "enterprise"
    spec["purpose"] = (state.get("purpose") or "").strip()
    if not spec.get("title") or spec.get("title") == "定制风控报告":
        spec["title"] = infer_title(chapters)
    state["spec"] = spec


def _spec_from_slots(state: dict) -> CustomReportSpec | None:
    """把累计槽位转成可提案的 spec；识别不到章节则弃权返回 None。

    优先：关键词命中章节 → 场景预设展开 → 弃权。
    范围（行业/全库/企业）只影响数据滤镜，不改写已识别的场景章节。
    """
    text = f"{state.get('purpose') or ''} {state.get('last_answer') or ''}".strip()
    scope_mode = detect_scope_mode(text, state)
    state["scope_mode"] = scope_mode

    chapters = match_chapters(text)
    if not chapters:
        chapters = chapters_from_custom_scene(text)
    if not chapters and has_scenario_keyword(text):
        # 兜底：通用场景词仍尽量展开为定制预设
        chapters = chapters_from_custom_scene(text)
    chapters = clamp_chapters_for_scope(chapters, scope_mode)
    if not chapters:
        return None
    spec = _spec_dict(state)
    # 合并已累计章节（最大化覆盖）
    for c in spec.get("chapters") or []:
        if c in CHAPTER_REGISTRY and c not in chapters:
            chapters.append(c)
    industry = spec.get("industry_l1") or _match_industry(text)
    province = spec.get("province") or _match_province(text)
    enterprises = _dedupe_enterprises(spec.get("enterprises") or []) or match_enterprises(text)
    if enterprises:
        state["scope_mode"] = "enterprise"
    title = spec.get("title") or ""
    if not title or title == "定制风控报告":
        title = infer_title(chapters)
    return CustomReportSpec(
        chapters=chapters,
        industry_l1=industry if industry in industry_l1_options() else None,
        province=province if province in province_options() else None,
        enterprises=enterprises,
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
        if c in CHAPTER_REGISTRY and c not in chapters:
            chapters.append(c)
    if chapters:
        acc["chapters"] = chapters
    if spec.industry_l1 in industry_l1_options():
        acc["industry_l1"] = spec.industry_l1
    if spec.province in province_options():
        acc["province"] = spec.province
    ent = _dedupe_enterprises(spec.enterprises)
    if ent:
        acc["enterprises"] = _dedupe_enterprises((acc.get("enterprises") or []) + ent)
    if spec.purpose:
        acc["purpose"] = spec.purpose
    state["spec"] = acc


def _merge_with_slots(spec: CustomReportSpec, state: dict) -> CustomReportSpec:
    """LLM 方案与规则累计槽位合并：LLM 为准，规则补漏遗漏的章节/范围（最大化覆盖）。"""
    acc = _spec_dict(state)
    chapters = list(spec.chapters or [])
    for c in acc.get("chapters") or []:
        if c in CHAPTER_REGISTRY and c not in chapters:
            chapters.append(c)
    industry = spec.industry_l1 or acc.get("industry_l1")
    province = spec.province or acc.get("province")
    enterprises = _dedupe_enterprises(spec.enterprises) or _dedupe_enterprises(acc.get("enterprises") or [])
    title = spec.title if (spec.title and spec.title != "定制风控报告") else infer_title(chapters)
    return CustomReportSpec(
        chapters=chapters,
        industry_l1=industry if industry in industry_l1_options() else None,
        province=province if province in province_options() else None,
        enterprises=enterprises,
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
            enterprises=spec.enterprises,
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
        "meta": {"actions": [{"label": "打开报告生成向导", "target": "/?wizard=1"}]},
        "llm": False,
    }


def rule_next_question(state: dict) -> str:
    """无 LLM 时的问题梯：先识别想解决什么（场景），再补范围。"""
    turn = int(state.get("turn") or 0)
    chapters = (_spec_dict(state).get("chapters") or [])
    if turn <= 1 or not chapters:
        return (
            "请告诉我这份报告主要想解决什么？例如财务健康、税务合规、发票舞弊、"
            "经营真实性、综合尽调、样本画像或风险预警——我会按对话识别场景并组合章节。"
        )
    if not (_spec_dict(state).get("industry_l1") or _spec_dict(state).get("enterprises")):
        if turn == 2:
            return (
                "还需要限定数据范围吗？可说「制造业」「广东」「企业3」或「全部样本」。"
            )
    return "需要调整章节组合吗？可直接说加减项（如「再加上税务」）；没有就说「确认生成」。"


def rule_turn(state: dict, answer: str) -> dict:
    """无 LLM 降级：从对话识别场景→章节，范围只作数据滤镜。"""
    state["scope_mode"] = detect_scope_mode(
        f"{state.get('purpose') or ''} {answer or ''}", state
    )
    spec = _spec_from_slots(state)
    if spec is not None:
        state["spec"] = spec.model_dump()
        return {
            "reply": proposal_text(spec),
            "followups": PROPOSE_FOLLOWUPS,
            "stage": "propose",
            "spec": spec,
            "meta": {"custom_proposal": spec.model_dump(), "scope_mode": state.get("scope_mode")},
            "llm": False,
        }
    return {
        "reply": (
            "我还没识别到明确场景。请直接说关注点，例如：财务健康、税务合规、"
            "发票舞弊、尽调、画像、预警；或点下面快捷项。"
        ),
        "followups": [
            "财务健康",
            "税务合规",
            "发票舞弊",
            "综合尽调",
            "样本库画像",
            "风险预警",
        ],
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
