"""报告场景模板：全量/行业两主题（画像 + 预警）× 个体体检（独立路径）。

产品定位（2026-08 锁定）：
- **个体企业**：单户财税票体检（enterprise 路径，非本 SCENARIOS）。
- **全量 / 行业**：同一类监管/机构用户；同构两主题——
  1. portrait（样本库画像）：均值/分位/占比/结构
  2. alert（风险预警）：阈值、命中条数、预警家数与信号

旧场景 key（financial/tax/…）经 _LEGACY_SCENARIO_MAP 归一到 portrait|alert，保证 API/历史兼容。
数据与评级永远来自 L0/L1（铁律），此处只决定「结构 + 语气」。
"""
from __future__ import annotations

import copy
import os
import re
from typing import Any

# 每章：功能是什么 → 由 judgment 填结论 → 证据链来自 claim.trace
ChapterSpec = dict[str, Any]

# 场景封面母题（前端据此渲染不同图形）+ 主色
# motif 取值：ledger / seal / magnifier / compass / badge
#
# 注意：各场景 "story" 字段仅为规划备注/文档说明，**不进入 L4 渲染**。
# 封面导语由 compose_story_from_chapters（claim → 文本）产出；无 claim → 弃权。

_PORTRAIT_SPEC: dict[str, Any] = {
    "title": "样本库画像报告",
    "subtitle": "结构分布 · 均值分布 · 信用与规模画像",
    "tier": "general",
    "story": "面向监管/机构的组合视角：刻画样本结构（地区、行业、信用），给出均值与分布结论，不作单户定性。",
    "data_focus": ["企业基础信息", "财务数据", "税务数据"],
    "cover": {"motif": "badge", "accent": "#6d28d9"},
    "kpis": [
        {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
        {"label": "覆盖地区", "metric": "region_count", "unit": "个", "source": "core_metrics"},
        {"label": "覆盖行业", "metric": "industry_count", "unit": "个", "source": "core_metrics"},
        {"label": "综合经营表现", "metric": "overall_score", "unit": "", "source": "assessment"},
    ],
    "chapters": [
        {
            "function": "score",
            "dimension": "region",
            "title": "地区信用结构",
            "purpose": "分地区信用表现对比，刻画结构梯度（结论导向，非样本脚注堆砌）。",
        },
        {
            "function": "trend",
            "dimension": "industry",
            "title": "行业规模与趋势",
            "purpose": "行业营收规模与主体数量分布，定位样本结构。",
        },
        {
            "function": "benchmark",
            "dimension": "industry",
            "title": "行业基准定位",
            "purpose": "样本均值对比行业基准，识别偏离。",
        },
        {
            "function": "score",
            "dimension": "overall",
            "title": "六维经营表现画像",
            "purpose": "样本六维均值画像，建立总体认知。",
        },
    ],
}

_ALERT_SPEC: dict[str, Any] = {
    "title": "风险预警报告",
    "subtitle": "预警阈值 · 命中家数 · 信号分布（匿名）",
    "tier": "general",
    "story": "面向监管/稽查预警：集中披露常规阈值、超阈命中家数与信号分布；主体匿名聚合，不输出具名企业名单。",
    "data_focus": ["税务数据", "发票数据", "财务数据", "企业基础信息"],
    "cover": {"motif": "magnifier", "accent": "#d32f2f"},
    "kpis": [
        {"label": "预警主体数", "metric": "flagged_count", "unit": "家", "source": "core_metrics"},
        {"label": "群体风险判断", "metric": "risk_level", "unit": "档", "source": "computed"},
        {"label": "舞弊信号", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
        {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
    ],
    "chapters": [
        {
            "function": "signal",
            "dimension": "signal",
            "title": "预警信号总览",
            "purpose": "命中规则、预警家数与多重风险叠加；写清常规阈值与超阈计数。",
        },
        {
            "function": "fraud",
            "dimension": "industry",
            "title": "发票异常预警",
            "purpose": "进销错配、红冲、集中度与序列缺口的命中分布。",
        },
        {
            "function": "tax",
            "dimension": "overall",
            "title": "税务合规预警",
            "purpose": "欠税、滞纳、违法与税负异常主体计数。",
        },
        {
            "function": "authenticity",
            "dimension": "overall",
            "title": "真实性交叉预警",
            "purpose": "多口径营收偏差超阈主体与勾稽异常。",
        },
    ],
}

# 主场景 + 旧 key 别名（深拷贝，避免共享可变 chapters）
SCENARIOS: dict[str, dict[str, Any]] = {
    "portrait": copy.deepcopy(_PORTRAIT_SPEC),
    "alert": copy.deepcopy(_ALERT_SPEC),
    # 兼容旧 API / 历史文件名 / 单测直接下标
    "profile": copy.deepcopy(_PORTRAIT_SPEC),
    "overview": copy.deepcopy(_PORTRAIT_SPEC),
    "financial": copy.deepcopy(_ALERT_SPEC),
    "tax": copy.deepcopy(_ALERT_SPEC),
    "fraud": copy.deepcopy(_ALERT_SPEC),
    "due_diligence": copy.deepcopy(_ALERT_SPEC),
}
# 兼容别名保留原标题，便于旧文案/下载名识别
SCENARIOS["profile"]["title"] = "样本库画像报告"
SCENARIOS["overview"]["title"] = "样本库画像报告"
SCENARIOS["financial"]["title"] = "风险预警报告"
SCENARIOS["tax"]["title"] = "风险预警报告"
SCENARIOS["fraud"]["title"] = "风险预警报告"
SCENARIOS["due_diligence"]["title"] = "风险预警报告"

# 场景中文名（含数据类侧重提示）
SCENARIO_LABELS = {
    "portrait": "样本库画像（结构统计）",
    "alert": "风险预警（阈值与命中分布）",
    "financial": "风险预警（兼容旧·财务）",
    "tax": "风险预警（兼容旧·税务）",
    "fraud": "风险预警（兼容旧·发票）",
    "due_diligence": "风险预警（兼容旧·尽调）",
    "profile": "样本库画像（兼容旧·画像）",
    "overview": "样本库画像（兼容旧·总览）",
    "custom": "定制风控报告（按范围引导）",
}

# 全量/行业向导与对话只推荐这两个主题
PORTFOLIO_SCENARIO_KEYS: tuple[str, ...] = ("portrait", "alert")

# 定制：组合视角允许的章节积木（画像 / 预警）
PORTFOLIO_PORTRAIT_CHAPTERS: frozenset[str] = frozenset({"score", "trend", "benchmark"})
PORTFOLIO_ALERT_CHAPTERS: frozenset[str] = frozenset({"signal", "fraud", "tax", "authenticity"})
PORTFOLIO_ALLOWED_CHAPTERS: frozenset[str] = PORTFOLIO_PORTRAIT_CHAPTERS | PORTFOLIO_ALERT_CHAPTERS

# ── 全中文指标：英文/技术术语 → 平实中文（铁律：所有指标都是中文，英文无法理解）──
ZH_SIGNAL_LABELS: dict[str, str] = {
    "scbm_mismatch": "进销错配",
    "red_invoice": "红字发票异常",
    "concentration": "集中度",
    "sequence_gap": "序列缺口",
}

ZH_INDUSTRY_LABELS: dict[str, str] = {
    "IT软件": "软件信息",
}

# 报告用户可见面禁词（规范书 §四 / §十二 FORBIDDEN_MARKERS）；CI 与审计脚本共用
# 注意：中文业务映射词（本福特定律、卡方值、平均绝对偏差…）允许出现；禁的是英文/技术原词
FORBIDDEN_MARKERS: tuple[str, ...] = (
    "证据链",
    "溯源",
    "回溯",
    "附录",
    "数据说明",
    "方法说明",
    "术语词典",
    "core_metrics",
    "Benford",
    "χ²",
    "MAD",
    "权重",
    "加权贡献",
    "综合评分",
    "综合均分",
    "真实性均分",
    "维度得分",
    "分位",
    "模型风险得分",
    "None",
    "n=",
    "N=",
    "ROE",
    "ROA",
    " vs ",
    "IT软件",
    "scbm_mismatch",
    "red_invoice",
    "concentration",
    "sequence_gap",
)

# 内部规则号不得出现在用户可见正文（规范书全中文 / 禁止内部字段）
_RULE_ID_RE = re.compile(r"\b[TARIF]-\d{2}\b")


def scan_forbidden_in_text(text: str) -> list[str]:
    """扫描单段文本命中的禁词 / 规则号；无命中返回空列表。"""
    if not text:
        return []
    hits: list[str] = []
    for m in FORBIDDEN_MARKERS:
        if m in text:
            hits.append(m)
    for m in _RULE_ID_RE.findall(text):
        hits.append(m)
    return hits


def strip_bullet_prefix(text: str) -> str:
    t = (text or "").strip()
    while t and t[0] in "-•●·＊*":
        t = t[1:].lstrip()
    return t


def chapter_conclusion_lines(ch: dict[str, Any]) -> list[str]:
    """章节结论：侧重业务判断/处置；有关键数字表时禁止复读全套家数与正文大段。"""
    import re

    narration = (ch.get("narration") or "").strip()
    claims = ch.get("claims") or []
    has_table = bool(ch.get("numeric_rows"))
    action_keys = ("建议", "优先", "核查", "应", "需", "启动", "排查", "调取", "交叉")
    judgment_keys = (
        "风险", "预警", "承压", "偏弱", "稳健", "建议", "优先", "核查",
        "叠加", "覆盖", "高企", "分化", "异常", "命中", "迹象",
    )

    def _is_table_echo(text: str) -> bool:
        """纯数值复述：数字/% 密度高且无判断/动作词。"""
        if not text:
            return True
        if any(k in text for k in action_keys) or any(k in text for k in judgment_keys):
            # 仍可能是「带建议的全量数字复述」——有表时若数字过多视作表回声
            if has_table:
                digit_n = sum(1 for c in text if c.isdigit())
                house_n = text.count("家")
                if digit_n >= 10 or house_n >= 3:
                    return True
            return False
        digit_n = sum(1 for c in text if c.isdigit() or c in "%.")
        return has_table and digit_n >= max(6, len(text) // 4)

    def _pick_from_claims() -> list[str]:
        action: list[str] = []
        judgment: list[str] = []
        seen: set[str] = set()
        for c in claims:
            text = strip_bullet_prefix(c.get("claim") or "")
            if not text or text in seen or _is_table_echo(text):
                continue
            seen.add(text)
            if any(k in text for k in action_keys):
                action.append(text)
            elif any(k in text for k in judgment_keys):
                judgment.append(text)
        lines = (action + judgment)[:2]
        if lines:
            return lines
        candidates = [
            strip_bullet_prefix(c.get("claim") or "")
            for c in claims
            if (c.get("claim") or "").strip()
        ]
        candidates = [t for t in candidates if t and not _is_table_echo(t)]
        if candidates:
            return [min(candidates, key=len)]
        return []

    def _action_from_narration(text: str) -> list[str]:
        """从长解读里只抽处置/判断句，去掉信号家数清单。"""
        sents = [s.strip() for s in re.split(r"(?<=[。！？；])", text) if s.strip()]
        action = [s for s in sents if any(k in s for k in action_keys)]
        if action:
            out: list[str] = []
            for s in action[-2:]:
                cleaned = re.sub(r"信号命中分布为[:：][^。；]*[。；]?", "", s)
                cleaned = re.sub(
                    r"(进销错配|集中度|序列缺口|红字发票异常)\s*\d+\s*家[，,、]?",
                    "",
                    cleaned,
                )
                cleaned = re.sub(r"[，、]{2,}", "，", cleaned).strip("，、；; ")
                if cleaned and len(cleaned) >= 8:
                    if not cleaned.endswith(("。", "！", "？")):
                        cleaned += "。"
                    out.append(cleaned)
            return out[:2] if out else [action[-1]]
        judgment = [
            s for s in sents if any(k in s for k in judgment_keys) and s.count("家") < 3
        ]
        return judgment[:1]

    picked = _pick_from_claims()
    if picked:
        return picked
    # 有表时禁止整段 narration 进结论（与正文重复）
    if has_table and narration:
        lines = _action_from_narration(narration)
        if lines:
            return [strip_bullet_prefix(x) for x in lines]
        return []
    if narration and not _is_table_echo(narration):
        # 无表：仍不整段堆砌，最多取末句动作/判断
        lines = _action_from_narration(narration)
        if lines:
            return [strip_bullet_prefix(x) for x in lines]
        return [strip_bullet_prefix(narration)]
    return []


def zh_signal(key: str) -> str:
    """舞弊信号英文键 → 中文标签；未知键原样返回。"""
    return ZH_SIGNAL_LABELS.get(key, key)


def zh_industry(label: str | None) -> str | None:
    """行业名转中文（仅展示层映射，不改库内已存值）。"""
    if not label:
        return label
    return ZH_INDUSTRY_LABELS.get(label, label)


def zh_report_title(stem: str) -> str:
    """从 slice_*/ent_* 报告 id 反解中文标题（下载文件名/封面编号兜底）。"""
    import re

    m = re.match(r"^(?:slice|ent)_(.+)_\d{8}_\d{6}(?:_[a-f0-9]{8})?$", stem, re.I)
    if not m:
        return "评估报告"
    if stem.lower().startswith("ent_"):
        return "企业风险披露报告"
    return SCENARIOS.get(m.group(1), {}).get("title") or "评估报告"


def zh_report_no(stem: str) -> str:
    """报告 id → 纯中文编号（日期+时间）；用于封面「报告编号」替代英文 id。"""
    import re

    m = re.search(r"_(\d{8})_(\d{6})", stem or "")
    if not m:
        return "评估报告"
    d, t = m.group(1), m.group(2)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}"


def business_level(score: float | None) -> str:
    """模型得分 → 业务话术（稳健/中等/偏弱），报告不暴露原始得分与权重。"""
    if score is None:
        return "中等"
    return "稳健" if score >= 70 else "偏弱" if score < 45 else "中等"

# ── 定制报告：可自由组合的章节词汇（L3 结构层）──
# AI 定制对话把用户诉求映射为 8 个可组合「功能」的有序子集，逐个复用既有章节 builder。
# value = (章节标题, 章节说明)。key 与 judgment_service 的 8 个 function 一一对应。
CUSTOM_CHAPTERS: dict[str, tuple[str, str]] = {
    "financial": ("财务健康", "财务四能力 + 勾稽真实性 + 同业对标"),
    "tax": ("税务合规", "税负 + 纳税准时率 + 欠税信号"),
    "fraud": ("发票舞弊", "进销错配/红冲/集中度/序列缺口"),
    "authenticity": ("经营真实性", "多口径营收差异交叉核对"),
    "signal": ("风险信号总览", "违法/偏差/信用/多重叠加"),
    "score": ("六维经营表现", "六个维度经营表现画像"),
    "benchmark": ("行业对标", "同行均值/同业对比"),
    "trend": ("营收趋势", "营收同比与行业对比"),
}

# 每个可组合章节默认的分析维度（对齐固定场景 SCENARIOS 里的既有用法）
CUSTOM_CHAPTER_DIMENSIONS: dict[str, str] = {
    "financial": "overall",
    "tax": "overall",
    "fraud": "industry",
    "authenticity": "overall",
    "signal": "signal",
    "score": "industry",
    "benchmark": "industry",
    "trend": "industry",
}

# 每个功能覆盖的「六维雷达」维度（铁律：雷达 ⊆ 正文解析维度）。
# score 仅在 dimension=overall（无行业筛选，全样本六维归因）时覆盖全部六维；其余为行业信用与纳税健康。
# 用途：雷达图渲染前按章节裁剪，杜绝「雷达展示风险维度但正文无对应解析」的三张皮问题。
FUNCTION_RADAR_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "financial": ("finance",),            # 财务四能力
    "tax": ("tax_health",),               # 税负/准时率/欠税
    "fraud": ("invoice",),                # 发票舞弊信号
    "authenticity": ("authenticity",),    # 多口径营收差异
    "benchmark": ("industry", "finance"),  # 行业地位 + 财务比率对标
    "trend": ("industry",),               # 营收规模/趋势
    "signal": ("tax_health",),            # 税务违法/偏差/信用信号
    "score": ("industry", "tax_health"),  # 行业信用与纳税健康（industry/region）
}


def radar_dimensions_for_chapters(chapters: list[dict[str, Any]]) -> list[str]:
    """报告章节覆盖的六维集合（按 DIMENSION_WEIGHTS 顺序）。

    铁律（claim 唯一化）：雷达图只展示正文确有解析的维度；无对应章节的维度（如法律合规）
    不画进雷达。
    """
    from app.services.assessment_weights import DIMENSION_WEIGHTS

    covered: set[str] = set()
    for ch in chapters:
        fn = ch.get("function")
        if fn == "score" and ch.get("dimension") == "overall":
            covered.update(DIMENSION_WEIGHTS)
        else:
            covered.update(FUNCTION_RADAR_DIMENSIONS.get(fn, ()))
    return [k for k in DIMENSION_WEIGHTS if k in covered]

# 章节关键词（规则侧兜底 + 数据驱动引导）：把用户自然语言映射到 8 个可组合章节。
# 更具体短语在前，避免「信用评分」被「评分」泛化吞掉；顺序只用于 find，匹配去重后按提及先后排序。
CUSTOM_CHAPTER_KEYWORDS: list[tuple[str, str]] = [
    ("财务健康", "financial"),
    ("盈利能力", "financial"),
    ("偿债能力", "financial"),
    ("现金流", "financial"),
    ("财务", "financial"),
    ("税务合规", "tax"),
    ("税负", "tax"),
    ("欠税", "tax"),
    ("纳税", "tax"),
    ("税务", "tax"),
    ("发票舞弊", "fraud"),
    ("进销错配", "fraud"),
    ("红冲", "fraud"),
    ("红字发票", "fraud"),
    ("发票", "fraud"),
    ("舞弊", "fraud"),
    ("欺诈", "fraud"),
    ("经营真实性", "authenticity"),
    ("经营真实", "authenticity"),
    ("真实性", "authenticity"),
    ("真伪", "authenticity"),
    ("造假", "authenticity"),
    ("虚开", "authenticity"),
    ("勾稽", "authenticity"),
    ("可信度", "authenticity"),
    ("benford", "authenticity"),
    ("风险信号", "signal"),
    ("风险预警", "signal"),
    ("预警", "signal"),
    ("信号", "signal"),
    ("告警", "signal"),
    ("风险等级", "score"),
    ("综合评分", "score"),
    ("综合分", "score"),
    ("信用评分", "score"),
    ("评分", "score"),
    ("打分", "score"),
    ("行业对比", "benchmark"),
    ("同业对标", "benchmark"),
    ("百分位", "benchmark"),
    ("同行均值", "benchmark"),
    ("对标", "benchmark"),
    ("同业", "benchmark"),
    ("基准", "benchmark"),
    ("营收趋势", "trend"),
    ("同比", "trend"),
    ("环比", "trend"),
    ("趋势", "trend"),
    ("走向", "trend"),
    ("走势", "trend"),
]

# ── L2 语气层：场景人格 + 去 AI 味（语气只改表达，不改评级/数字，铁律）──
# 同一批数据按场景换「身份/文风」，但结论与评级仍由 L0/L1 统一决定。
TONE_PROFILES: dict[str, dict[str, str]] = {
    "portrait": {
        "persona": "组合画像分析师",
        "style": "风控专家口吻：结论前置；重结构、分布与占比，不作单户定性。",
    },
    "alert": {
        "persona": "风险预警分析师",
        "style": "风控专家口吻：结论前置；写清阈值、命中条数与预警家数，给可核查动作。",
    },
    "financial": {
        "persona": "风险预警分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；紧扣数字含义与偿债/盈利压力，短句，一句一个判断。",
    },
    "tax": {
        "persona": "风险预警分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；突出合规风险与补税/滞纳后果，短句。",
    },
    "fraud": {
        "persona": "风险预警分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；聚焦异常证据与可疑主体，只陈述证据不妄下结论。",
    },
    "due_diligence": {
        "persona": "风险预警分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；风险分级清晰，可执行、可核查。",
    },
    "profile": {
        "persona": "组合画像分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；重分布与占比，不渲染情绪。",
    },
    "overview": {
        "persona": "组合画像分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；跨场景摘要并置，突出关键风险。",
    },
    "enterprise": {
        "persona": "财务分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；对单个主体下判断，点明风险点与建议。",
    },
    "custom": {
        "persona": "风控定制顾问",
        "style": "风控专家口吻：结论前置；先确认范围（个体/行业/全库），组合视角只拼画像与预警模块。",
    },
}

# 去 AI 味：统一禁用套话/过渡词（各场景共用，避免「AI 腔」与「学术汇报腔」）
BANNED_AI_PHRASES = (
    "首先，其次，再次，最后，综上所述，总而言之，总的说来，值得注意的是，"
    "由此可见，不难发现，作为一个，需要指出的是，换言之，换句话说，"
    "在这个背景下，随着，可以说，总的来说，接下来，基于上述分析，"
    "本报告，该维度，分析显示，数据显示，本文，本研究，综上，"
    "从数据来看，整体来看，总体而言，值得关注的是"
)


# 对话快捷：默认画像；可指定画像/预警及旧场景关键词
SCENARIO_ALIASES = {
    "画像": "portrait",
    "样本库画像": "portrait",
    "结构": "portrait",
    "分布": "portrait",
    "基础信息": "portrait",
    "企业概况": "portrait",
    "概览": "portrait",
    "总览": "portrait",
    "汇总": "portrait",
    "综合总览": "portrait",
    "预警": "alert",
    "风险预警": "alert",
    "告警": "alert",
    "监察": "alert",
    "稽查": "alert",
    "财务": "alert",
    "财务健康": "alert",
    "盈利": "alert",
    "偿债": "alert",
    "现金流": "alert",
    "基本面": "alert",
    "税务": "alert",
    "合规": "alert",
    "税负": "alert",
    "欠税": "alert",
    "纳税": "alert",
    "发票": "alert",
    "舞弊": "alert",
    "欺诈": "alert",
    "红冲": "alert",
    "进销": "alert",
    "尽调": "alert",
    "综合": "alert",
    "全面": "alert",
    "趋势": "alert",
    "通识": "alert",
}

# 旧场景 key → 画像|预警
_LEGACY_SCENARIO_MAP = {
    "general": "alert",
    "fundamental": "alert",
    "custom": "alert",
    "financial": "alert",
    "tax": "alert",
    "fraud": "alert",
    "due_diligence": "alert",
    "profile": "portrait",
    "overview": "portrait",
}

DEFAULT_SCENARIO = "portrait"


def _canonical(key: str | None) -> str:
    """旧 key 归一化到 portrait|alert；未知 key 保持原样（调用方决定是否报错）。"""
    if not key:
        return DEFAULT_SCENARIO
    mapped = _LEGACY_SCENARIO_MAP.get(key, key)
    if mapped in ("portrait", "alert"):
        return mapped
    return mapped


def has_scenario_keyword(query: str | None) -> bool:
    """query 是否显式命中某个场景关键词（用于区分「生成报告」=罗列路径 对比指定场景=直接生成）。"""
    q = query or ""
    return any(kw in q for kw in SCENARIO_ALIASES)


def scenario_path_prompts() -> list[str]:
    """罗列生成路径（供对话引导）：全量/行业两主题 + 提示个体走指定企业。"""
    return [
        f"生成{SCENARIOS[k]['title']}"
        for k in PORTFOLIO_SCENARIO_KEYS
        if k in SCENARIOS
    ] + ["生成指定企业体检报告"]


def resolve_scenario(query: str | None = None, scenario: str | None = None) -> str:
    if scenario:
        key = _canonical(scenario)
        if key in SCENARIOS:
            return key
        raise ValueError(f"未知报告场景: {scenario}；可选: {', '.join(sorted(PORTFOLIO_SCENARIO_KEYS))}")
    q = query or ""
    for kw, key in sorted(SCENARIO_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if kw in q:
            return _canonical(key)
    return DEFAULT_SCENARIO


def get_scenario(key: str) -> dict[str, Any]:
    return SCENARIOS.get(_canonical(key)) or SCENARIOS[DEFAULT_SCENARIO]


def get_scenario_tier(key: str) -> str:
    """通用模板 general（免费） 对比定制 premium（付费）。五场景均为 general。"""
    return (SCENARIOS.get(_canonical(key)) or SCENARIOS[DEFAULT_SCENARIO]).get("tier", "general")


def get_scenario_label(key: str) -> str:
    return SCENARIO_LABELS.get(key) or SCENARIO_LABELS.get(_canonical(key), key)


def scope_label(industry_l1: str | None = None, province: str | None = None) -> str:
    """范围前缀（行业/地区），用于报告标题；行业经中文映射，避免「IT软件」等禁词上封面。"""
    if industry_l1:
        return zh_industry(industry_l1) or industry_l1
    return province or ""


def sanitize_surface_industry_terms(text: str | None) -> str:
    """用户可见文案：行业代码中文化 + 内部开发残留词替换。"""
    if not text:
        return ""
    out = str(text)
    # 长键优先，避免部分替换
    for raw, zh in sorted(ZH_INDUSTRY_LABELS.items(), key=lambda kv: len(kv[0]), reverse=True):
        if raw in out:
            out = out.replace(raw, zh)
    # 内部开发术语 → 业务语言（LLM/旧模板残留）
    for raw, zh in (
        ("预警积木", "预警类型"),
        ("章节积木", "章节模块"),
        ("场景积木", "场景模块"),
        ("组合积木", "组合模块"),
        ("均值分位", "均值分布"),
        ("同业分位", "同业对比位置"),
        ("百分位", "相对位置"),
        ("分位数", "相对位置"),
    ):
        if raw in out:
            out = out.replace(raw, zh)
    # 单独「分位」残留（禁词表硬拒）；避免误伤已替换词
    if "分位" in out:
        out = out.replace("分位", "分布")
    return out


def get_scenario_cover(key: str) -> dict[str, str]:
    """场景封面母题 + 主色，供封面图形渲染（L4）。"""
    spec = SCENARIOS.get(_canonical(key)) or SCENARIOS[DEFAULT_SCENARIO]
    return dict(spec.get("cover") or {"motif": "compass", "accent": "#003366"})


def get_scenario_tone(key: str) -> dict[str, str]:
    """场景语气（L2）：报告解读/摘要的身份与文风；未知 key 回退综合尽调。"""
    if key in TONE_PROFILES:
        return TONE_PROFILES[key]
    return TONE_PROFILES.get(_canonical(key), TONE_PROFILES[DEFAULT_SCENARIO])


def compose_purpose_from_claims(
    structural_purpose: str,
    claims: list[Any],
) -> str:
    """章功能说明：有 claim 才保留结构目的句；无 claim → 弃权（管道：无 message 无文本）。"""
    n = 0
    for c in claims or []:
        text = c.get("claim") if isinstance(c, dict) else getattr(c, "claim", None)
        if text:
            n += 1
    if n <= 0:
        return "本章无有效样本结论，内容弃权。"
    base = (structural_purpose or "").strip()
    return base or f"本章共 {n} 条可溯源结论。"


def compose_story_from_chapters(chapters: list[dict[str, Any]]) -> str:
    """封面导语仅由各章 claim 拼装（document plan → surface）。无 claim → 弃权，禁止静态营销句顶替。"""
    fragments: list[str] = []
    for ch in chapters or []:
        for c in ch.get("claims") or []:
            text = (c.get("claim") if isinstance(c, dict) else "") or ""
            text = str(text).strip()
            if not text:
                continue
            if not text.endswith(("。", "！", "？")):
                text += "。"
            fragments.append(text)
            break
        if len(fragments) >= 4:
            break
    if not fragments:
        return "当前切片无有效结论，报告导语弃权（不编造）。"
    return "".join(fragments)


class PremiumReportLocked(Exception):
    """定制报告（付费层级）在开发期被隔离，尚未开放。"""


def is_premium_locked() -> bool:
    """开发期付费隔离开关。

    默认锁定（false）：premium 场景仅展示层级、不产出报告。
    上线后置 ``PREMIUM_REPORT_ENABLED=true`` 即可开放付费定制链路。
    """
    return os.getenv("PREMIUM_REPORT_ENABLED", "false").lower() not in ("1", "true", "yes")


# ── 术语词典（附录）：已废弃。报告正文严禁算法科普（不解释模型内部计算逻辑），
# 信号键一律经 zh_signal()/zh_industry() 直接转业务语言，不再提供黑话→中文对照表。

