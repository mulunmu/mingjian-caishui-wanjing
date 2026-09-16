"""报告场景模板：四业务场景（放贷/评级/预警/稽查）× 个体体检。

产品定位（2026-09 M4）：
- **个体企业**：单户财税票体检（enterprise 路径，非本 SCENARIOS）。
- **全量 / 行业**：四业务场景——
  1. loan（放贷）：能不能贷 / 额度与附加条件
  2. rating（评级）：信用等级与结构画像（承接原 portrait）
  3. warn（预警）：阈值、命中与异常分布（承接原 alert）
  4. audit（稽查）：哪里可疑、优先核查什么

旧 key（portrait/alert/financial/…）经 _LEGACY_SCENARIO_MAP 归一到四场景，保证 API/历史兼容。
数据与评级永远来自 L0/L1（铁律），此处只决定「结构 + 语气」。
"""
from __future__ import annotations

import copy
import os
import re
from typing import Any

# 每章：功能是什么 → 由 judgment 填结论 → 证据链来自 claim.trace
ChapterSpec = dict[str, Any]

# 场景封面母题 + 主色（与 cover_frame_*.svg 强调色对齐）
# motif 取值：ledger / seal / magnifier / compass / badge
#
# 注意：各场景 "story" 字段仅为规划备注/文档说明，**不进入 L4 渲染**。
# 封面导语由 compose_story_from_chapters（claim → 文本）产出；无 claim → 弃权。

_RATING_SPEC: dict[str, Any] = {
    "title": "评级研判报告",
    "subtitle": "信用结构 · 等级信号 · 六维经营表现",
    "tier": "general",
    "governing_question": "群体信用结构？谁可授信？",
    "story": "面向评级/授信人员：用财税票经营数据说明信用处在什么水平、结构强弱在哪。",
    "data_focus": ["企业基础信息", "财务数据", "税务数据"],
    "cover": {"motif": "badge", "accent": "#A18A5F", "frame": "rating"},
    "kpis": [
        {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
        {"label": "覆盖地区", "metric": "region_count", "unit": "个", "source": "core_metrics"},
        {"label": "覆盖行业", "metric": "industry_count", "unit": "个", "source": "core_metrics"},
        {"label": "综合经营表现", "metric": "overall_score", "unit": "", "source": "assessment"},
    ],
    "chapters": [
        {"function": "score", "dimension": "region", "title": "地区信用结构", "purpose": "分地区信用表现对比，刻画结构梯度（结论导向）。"},
        {"function": "trend", "dimension": "industry", "title": "行业规模与趋势", "purpose": "行业营收规模与主体数量分布，定位样本结构。"},
        {"function": "benchmark", "dimension": "industry", "title": "行业基准定位", "purpose": "样本均值对比行业基准，识别偏离。"},
        {"function": "score", "dimension": "overall", "title": "六维经营表现画像", "purpose": "样本六维均值画像，建立总体认知。"},
    ],
}

_LOAN_SPEC: dict[str, Any] = {
    "title": "放贷研判报告",
    "subtitle": "能不能贷 · 额度逻辑 · 附加条件",
    "tier": "general",
    "governing_question": "能不能放贷？附加什么条件？",
    "story": "面向信贷人员：用经营与发票信号回答能不能贷、额度要不要收紧、附加条件写什么。",
    "data_focus": ["财务数据", "发票数据", "税务数据", "企业基础信息"],
    "cover": {"motif": "compass", "accent": "#3A6EA5", "frame": "loan"},
    "kpis": [
        {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
        {"label": "群体风险判断", "metric": "risk_level", "unit": "档", "source": "computed"},
        {"label": "综合经营表现", "metric": "overall_score", "unit": "", "source": "assessment"},
        {"label": "舞弊信号", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
    ],
    "chapters": [
        {"function": "score", "dimension": "overall", "title": "放贷综合判断", "purpose": "先给能不能贷的总体判断，再落到经营与发票信号。"},
        {"function": "fraud", "dimension": "industry", "title": "发票与进销信号", "purpose": "进货销货是否对得上、冲红与开票连续性——放贷附加条件的主要依据。"},
        {"function": "authenticity", "dimension": "overall", "title": "收入真实性", "purpose": "申报/开票/财报是否同向，避免额度建立在虚增营收上。"},
        {"function": "benchmark", "dimension": "industry", "title": "同业对照与额度参考", "purpose": "对照行业均值，提示额度上限与收紧理由。"},
    ],
}

_WARN_SPEC: dict[str, Any] = {
    "title": "风险预警报告",
    "subtitle": "预警阈值 · 命中家数 · 信号分布（匿名）",
    "tier": "general",
    "governing_question": "风险在哪？哪些企业该预警？",
    "story": "面向监测/预警：集中披露阈值、超阈命中家数与信号分布；主体匿名聚合，不输出具名名单。",
    "data_focus": ["税务数据", "发票数据", "财务数据", "企业基础信息"],
    "cover": {"motif": "magnifier", "accent": "#C87F1F", "frame": "warn"},
    "kpis": [
        {"label": "预警主体数", "metric": "flagged_count", "unit": "家", "source": "core_metrics"},
        {"label": "群体风险判断", "metric": "risk_level", "unit": "档", "source": "computed"},
        {"label": "舞弊信号", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
        {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
    ],
    "chapters": [
        {"function": "signal", "dimension": "signal", "title": "预警信号总览", "purpose": "命中规则、预警家数与多重风险叠加；写清常规阈值与超阈计数。"},
        {"function": "fraud", "dimension": "industry", "title": "发票异常预警", "purpose": "进货销货对不上、冲红、集中度与开票断续的命中分布。"},
        {"function": "tax", "dimension": "overall", "title": "税务合规预警", "purpose": "欠税、滞纳、违法与交税占比异常主体计数。"},
        {"function": "authenticity", "dimension": "overall", "title": "真实性交叉预警", "purpose": "多口径营收偏差超阈主体与勾稽异常。"},
    ],
}

_AUDIT_SPEC: dict[str, Any] = {
    "title": "稽查线索报告",
    "subtitle": "可疑点 · 优先核查 · 可照做动作",
    "tier": "general",
    "governing_question": "哪些可疑？优先查谁？查什么？",
    "story": "面向稽查人员：指出哪里可疑、该先查什么，给出可照做的核查动作（匿名聚合）。",
    "data_focus": ["发票数据", "税务数据", "财务数据"],
    "cover": {"motif": "seal", "accent": "#A03C35", "frame": "audit"},
    "kpis": [
        {"label": "可疑信号主体", "metric": "flagged_count", "unit": "家", "source": "core_metrics"},
        {"label": "舞弊信号", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
        {"label": "群体风险判断", "metric": "risk_level", "unit": "档", "source": "computed"},
        {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
    ],
    "chapters": [
        {"function": "fraud", "dimension": "industry", "title": "优先核查：发票异常", "purpose": "红冲、进销对不上、开票断续——稽查第一下钻点。"},
        {"function": "authenticity", "dimension": "overall", "title": "优先核查：账票不一致", "purpose": "申报与开票、财报口径是否同向。"},
        {"function": "tax", "dimension": "overall", "title": "税务合规疑点", "purpose": "欠税/滞纳/交税占比异常，作为第二核查队列。"},
        {"function": "signal", "dimension": "signal", "title": "信号叠加与名单策略", "purpose": "多重信号叠加的匿名命中分布，提示抽查优先级。"},
    ],
}

# 兼容旧名
_PORTRAIT_SPEC = _RATING_SPEC
_ALERT_SPEC = _WARN_SPEC

SCENARIOS: dict[str, dict[str, Any]] = {
    "loan": copy.deepcopy(_LOAN_SPEC),
    "rating": copy.deepcopy(_RATING_SPEC),
    "warn": copy.deepcopy(_WARN_SPEC),
    "audit": copy.deepcopy(_AUDIT_SPEC),
    "portrait": copy.deepcopy(_RATING_SPEC),
    "alert": copy.deepcopy(_WARN_SPEC),
    "profile": copy.deepcopy(_RATING_SPEC),
    "overview": copy.deepcopy(_RATING_SPEC),
    "financial": copy.deepcopy(_WARN_SPEC),
    "tax": copy.deepcopy(_WARN_SPEC),
    "fraud": copy.deepcopy(_AUDIT_SPEC),
    "due_diligence": copy.deepcopy(_WARN_SPEC),
}
SCENARIOS["portrait"]["title"] = "评级研判报告"
SCENARIOS["profile"]["title"] = "评级研判报告"
SCENARIOS["overview"]["title"] = "评级研判报告"
SCENARIOS["alert"]["title"] = "风险预警报告"
SCENARIOS["financial"]["title"] = "风险预警报告"
SCENARIOS["tax"]["title"] = "风险预警报告"
SCENARIOS["fraud"]["title"] = "稽查线索报告"
SCENARIOS["due_diligence"]["title"] = "风险预警报告"

SCENARIO_LABELS = {
    "loan": "放贷研判",
    "rating": "评级研判",
    "warn": "风险预警",
    "audit": "稽查线索",
    "portrait": "评级研判（兼容旧·画像）",
    "alert": "风险预警（兼容旧·预警）",
    "financial": "风险预警（兼容旧·财务）",
    "tax": "风险预警（兼容旧·税务）",
    "fraud": "稽查线索（兼容旧·发票）",
    "due_diligence": "风险预警（兼容旧·尽调）",
    "profile": "评级研判（兼容旧·画像）",
    "overview": "评级研判（兼容旧·总览）",
    "custom": "定制风控报告（按范围引导）",
    "enterprise": "企业体检",
}

PORTFOLIO_SCENARIO_KEYS: tuple[str, ...] = ("loan", "rating", "warn", "audit")

PORTFOLIO_PORTRAIT_CHAPTERS: frozenset[str] = frozenset({"score", "trend", "benchmark"})
PORTFOLIO_ALERT_CHAPTERS: frozenset[str] = frozenset({"signal", "fraud", "tax", "authenticity"})
PORTFOLIO_ALLOWED_CHAPTERS: frozenset[str] = PORTFOLIO_PORTRAIT_CHAPTERS | PORTFOLIO_ALERT_CHAPTERS
PORTFOLIO_LOAN_CHAPTERS: frozenset[str] = frozenset({"score", "fraud", "authenticity", "benchmark"})
PORTFOLIO_AUDIT_CHAPTERS: frozenset[str] = frozenset({"fraud", "authenticity", "tax", "signal"})

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
    if not picked:
        # 有表时禁止整段 narration 进结论（与正文重复）
        if has_table and narration:
            lines = _action_from_narration(narration)
            if lines:
                picked = [strip_bullet_prefix(x) for x in lines]
        elif narration and not _is_table_echo(narration):
            # 无表：仍不整段堆砌，最多取末句动作/判断
            lines = _action_from_narration(narration)
            if lines:
                picked = [strip_bullet_prefix(x) for x in lines]
            else:
                picked = [strip_bullet_prefix(narration)]

    if not picked:
        return []

    # 结论 + 为什么：首条作结论，次条或同条说明作原因
    out: list[str] = []
    head = picked[0].rstrip("。")
    why = picked[1].rstrip("。") if len(picked) > 1 else ""
    if why and "为什么" not in head:
        out.append(f"结论：{head}。为什么：{why}。")
    elif "为什么" in head or head.startswith("结论"):
        out.append(head if head.endswith(("。", "！", "？")) else head + "。")
    else:
        out.append(f"结论：{head}。")
    for extra in picked[2:]:
        out.append(extra if extra.endswith(("。", "！", "？")) else extra + "。")
    return out[:3]


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


def metric_level(score: float | None = None, *, flagged: bool | None = None) -> str:
    """关键数字旁标签：偏强 / 正常 / 预警（小白可读）。"""
    if flagged is True:
        return "预警"
    if score is None:
        return "正常"
    if score >= 70:
        return "偏强"
    if score < 45:
        return "预警"
    return "正常"


def cover_frame_key(scenario: str | None) -> str:
    """封面回纹框：loan/rating/warn/audit；个体体检默认 rating。"""
    key = _canonical(scenario) if scenario and scenario != "enterprise" else "rating"
    if scenario == "enterprise":
        return "rating"
    return key if key in _CANONICAL_KEYS else "rating"


def actionable_advice(lines: list[str] | None, *, scenario: str | None = None) -> list[str]:
    """把空泛建议收成能照做的动作句；已是动作句则保留。"""
    raw = [strip_bullet_prefix(x) for x in (lines or []) if (x or "").strip()]
    action_keys = ("核查", "核对", "导出", "抽查", "压降", "收紧", "对照", "优先", "调取")
    out: list[str] = []
    for line in raw:
        if any(k in line for k in action_keys):
            out.append(line if line.endswith(("。", "！", "？")) else line + "。")
        else:
            out.append(f"建议：对照关键数字核对「{line.rstrip('。')}」，并留下可复核记录。")
    if out:
        return out[:4]
    sc = _canonical(scenario) if scenario and scenario != "enterprise" else (scenario or "rating")
    defaults = {
        "loan": "建议：按行业均值设额度上限，并把开票连续性、进销是否对得上作为放贷附加条件。",
        "rating": "建议：对照官方扣分项核对冲红次数与申报差异，再确认等级口径。",
        "warn": "建议：把最高信号行业/群体拉出来，核对近 3 个月开票与申报是否同向。",
        "audit": "建议：优先抽查红冲发票对应销售方名单，并核对申报收入与开票收入是否一致。",
        "enterprise": "建议：先处理最高风险信号，再回头看综合经营表现是否回升。",
    }
    return [defaults.get(sc or "rating", defaults["rating"])]

# ── 定制报告：可自由组合的章节词汇（L3 结构层）──
# M3：旧常量改为 CHAPTER_REGISTRY 兼容别名，所有调用点自动兼容。
# CUSTOM_CHAPTERS / CUSTOM_CHAPTER_DIMENSIONS / FUNCTION_RADAR_DIMENSIONS 定义在 CHAPTER_REGISTRY 之后。


# ── M0 冻结：章节工具表（Chapter Tools）──
# 收敛 CUSTOM_CHAPTERS + CUSTOM_CHAPTER_DIMENSIONS + FUNCTION_RADAR_DIMENSIONS 为一张注册表。
# 加新章节 = 写一个新引擎函数 + 在此注册表加一条记录，不再改散落的四处配置。
CHAPTER_REGISTRY: dict[str, dict[str, Any]] = {
    "financial": {
        "title": "财务健康",
        "desc": "财务四能力 + 勾稽真实性 + 同业对标",
        "engine_fn": "build_financial_claims",
        "default_dimension": "overall",
        "radar_dims": ("finance",),
        "data_shapes": ["categorical_distribution", "tabular_rows"],
        "keywords": ["财务健康", "盈利能力", "偿债能力", "现金流", "财务"],
        "kpis": [
            {"label": "利润率", "metric": "profit_margin", "unit": "%"},
            {"label": "营收同比", "metric": "revenue_yoy", "unit": "%"},
            {"label": "资产负债率", "metric": "debt_ratio", "unit": "%"},
            {"label": "现金流水平", "metric": "cash_flow_level", "unit": ""},
        ],
    },
    "tax": {
        "title": "税务合规",
        "desc": "税负 + 纳税准时率 + 欠税信号",
        "engine_fn": "build_tax_claims",
        "default_dimension": "overall",
        "radar_dims": ("tax_health",),
        "data_shapes": ["categorical_distribution"],
        "keywords": ["税务合规", "税负", "欠税", "纳税", "税务"],
        "kpis": [
            {"label": "纳税准时率", "metric": "tax_on_time_rate", "unit": ""},
            {"label": "增值税税负率", "metric": "vat_burden", "unit": "%"},
            {"label": "所得税税负率", "metric": "income_tax_burden", "unit": "%"},
            {"label": "欠税记录", "metric": "tax_arrears_cnt", "unit": "条"},
        ],
    },
    "fraud": {
        "title": "发票舞弊",
        "desc": "进销错配/红冲/集中度/序列缺口",
        "engine_fn": "build_fraud_claims",
        "default_dimension": "industry",
        "radar_dims": ("invoice",),
        "data_shapes": ["hierarchical_stages", "categorical_distribution", "tabular_rows"],
        "keywords": ["发票舞弊", "进销错配", "红冲", "红字发票", "发票", "舞弊", "欺诈"],
        "kpis": [
            {"label": "舞弊预警主体数", "metric": "flagged_count", "unit": "家"},
            {"label": "舞弊综合分", "metric": "fraud_composite_score", "unit": "分"},
        ],
    },
    "authenticity": {
        "title": "经营真实性",
        "desc": "多口径营收差异交叉核对",
        "engine_fn": "build_authenticity_claims",
        "default_dimension": "overall",
        "radar_dims": ("authenticity",),
        "data_shapes": ["proportion_buckets", "tabular_rows"],
        "keywords": ["经营真实性", "经营真实", "真实性", "真伪", "造假", "虚开", "勾稽", "可信度", "benford"],
        "kpis": [
            {"label": "营收偏差", "metric": "revenue_deviation", "unit": ""},
            {"label": "可疑主体数", "metric": "suspicious_count", "unit": "家"},
        ],
    },
    "signal": {
        "title": "风险信号总览",
        "desc": "违法/偏差/信用/多重叠加",
        "engine_fn": "build_signal_claims",
        "default_dimension": "signal",
        "radar_dims": ("tax_health",),
        "data_shapes": ["matrix_heatmap", "proportion_buckets", "hierarchical_stages"],
        "keywords": ["风险信号", "风险预警", "预警", "信号", "告警"],
        "kpis": [
            {"label": "风险信号主体数", "metric": "signal_total", "unit": "家"},
            {"label": "税务违法", "metric": "tax_violation", "unit": "家"},
            {"label": "高偏差", "metric": "high_dev", "unit": "家"},
            {"label": "低信用", "metric": "low_credit", "unit": "家"},
        ],
    },
    "score": {
        "title": "六维经营表现",
        "desc": "六个维度经营表现画像",
        "engine_fn": "build_score_claims",
        "default_dimension": "industry",
        "radar_dims": ("industry", "tax_health"),
        "data_shapes": ["multi_dim_vector", "categorical_distribution"],
        "keywords": ["风险等级", "综合评分", "综合分", "信用评分", "评分", "打分"],
        "kpis": [
            {"label": "综合经营表现", "metric": "overall_score", "unit": "分"},
            {"label": "税务健康", "metric": "tax_health_score", "unit": "分"},
            {"label": "经营真实性", "metric": "authenticity_score", "unit": "分"},
            {"label": "发票健康", "metric": "invoice_score", "unit": "分"},
        ],
    },
    "benchmark": {
        "title": "行业对标",
        "desc": "同行均值/同业对比",
        "engine_fn": "build_benchmark_claims",
        "default_dimension": "industry",
        "radar_dims": ("industry", "finance"),
        "data_shapes": ["categorical_distribution"],
        "keywords": ["行业对比", "同业对标", "百分位", "同行均值", "对标", "同业", "基准"],
        "kpis": [
            {"label": "行业对标", "metric": "peer_industry_percentile", "unit": ""},
            {"label": "地区对标", "metric": "peer_province_percentile", "unit": ""},
        ],
    },
    "trend": {
        "title": "营收趋势",
        "desc": "营收同比与行业对比",
        "engine_fn": "build_trend_industry_claims",
        "default_dimension": "industry",
        "radar_dims": ("industry",),
        "data_shapes": ["ordered_series"],
        "keywords": ["营收趋势", "同比", "环比", "趋势", "走向", "走势"],
        "kpis": [
            {"label": "营收同比", "metric": "revenue_yoy", "unit": "%"},
        ],
    },
}

# M3：旧常量改为 CHAPTER_REGISTRY 兼容别名
CUSTOM_CHAPTERS: dict[str, tuple[str, str]] = {k: (v["title"], v["desc"]) for k, v in CHAPTER_REGISTRY.items()}
CUSTOM_CHAPTER_DIMENSIONS: dict[str, str] = {k: v["default_dimension"] for k, v in CHAPTER_REGISTRY.items()}
FUNCTION_RADAR_DIMENSIONS: dict[str, tuple[str, ...]] = {k: v["radar_dims"] for k, v in CHAPTER_REGISTRY.items()}
CUSTOM_CHAPTER_KEYWORDS: list[tuple[str, str]] = [
    (kw, k) for k, v in CHAPTER_REGISTRY.items() for kw in v.get("keywords", [])
]


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
            covered.update((CHAPTER_REGISTRY.get(fn) or {}).get("radar_dims", ()))
    return [k for k in DIMENSION_WEIGHTS if k in covered]

# ── L2 语气层：场景人格 + 去 AI 味（语气只改表达，不改评级/数字，铁律）──
# 同一批数据按场景换「身份/文风」，但结论与评级仍由 L0/L1 统一决定。
TONE_PROFILES: dict[str, dict[str, str]] = {
    "loan": {
        "persona": "信贷风控顾问",
        "style": "风控专家口吻：结论前置；回答能不能贷、额度要不要收紧、附加条件写什么。",
    },
    "rating": {
        "persona": "评级分析师",
        "style": "风控专家口吻：结论前置；重信用结构、等级信号与分布，不作空泛定性。",
    },
    "warn": {
        "persona": "风险预警分析师",
        "style": "风控专家口吻：结论前置；写清阈值、命中条数与预警家数，给可核查动作。",
    },
    "audit": {
        "persona": "稽查线索分析师",
        "style": "风控专家口吻：结论前置；指出哪里可疑、该先查什么，给可照做的核查动作。",
    },
    "portrait": {
        "persona": "评级分析师",
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
        "persona": "稽查线索分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；聚焦异常证据与可疑主体，只陈述证据不妄下结论。",
    },
    "due_diligence": {
        "persona": "风险预警分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；风险分级清晰，可执行、可核查。",
    },
    "profile": {
        "persona": "评级分析师",
        "style": "风控专家口吻：结论前置、判断直接、给可执行动作；重分布与占比，不渲染情绪。",
    },
    "overview": {
        "persona": "评级分析师",
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
    "放贷": "loan",
    "授信": "loan",
    "批贷": "loan",
    "能不能贷": "loan",
    "评级": "rating",
    "信用等级": "rating",
    "纳税信用": "rating",
    "画像": "rating",
    "样本库画像": "rating",
    "结构": "rating",
    "分布": "rating",
    "基础信息": "rating",
    "企业概况": "rating",
    "概览": "rating",
    "总览": "rating",
    "汇总": "rating",
    "综合总览": "rating",
    "预警": "warn",
    "风险预警": "warn",
    "告警": "warn",
    "监察": "warn",
    "稽查": "audit",
    "核查": "audit",
    "可疑": "audit",
    "财务": "warn",
    "财务健康": "warn",
    "盈利": "warn",
    "偿债": "loan",
    "现金流": "loan",
    "基本面": "rating",
    "税务": "warn",
    "合规": "warn",
    "税负": "warn",
    "欠税": "audit",
    "纳税": "rating",
    "发票": "audit",
    "舞弊": "audit",
    "欺诈": "audit",
    "红冲": "audit",
    "进销": "audit",
    "尽调": "warn",
    "综合": "warn",
    "全面": "warn",
    "趋势": "rating",
    "通识": "warn",
}

# 旧场景 key → 四业务场景
_LEGACY_SCENARIO_MAP = {
    "general": "warn",
    "fundamental": "warn",
    "custom": "warn",
    "financial": "warn",
    "tax": "warn",
    "fraud": "audit",
    "due_diligence": "warn",
    "profile": "rating",
    "overview": "rating",
    "portrait": "rating",
    "alert": "warn",
}

DEFAULT_SCENARIO = "rating"
_CANONICAL_KEYS = frozenset({"loan", "rating", "warn", "audit"})


def _canonical(key: str | None) -> str:
    """旧 key 归一化到 loan|rating|warn|audit；未知 key 保持原样（调用方决定是否报错）。"""
    if not key:
        return DEFAULT_SCENARIO
    mapped = _LEGACY_SCENARIO_MAP.get(key, key)
    if mapped in _CANONICAL_KEYS:
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
    return dict(spec.get("cover") or {"motif": "compass", "accent": "#152446"})


def get_scenario_tone(key: str) -> dict[str, str]:
    """场景语气（L2）：报告解读/摘要的身份与文风；未知 key 回退综合尽调。

    返回 dict 包含 persona/style/scenario 三键；scenario 用于统一 PERSONA 注入
    （红线 §4：报告层与对话层共用同一份 PERSONA，scenario 变体叠加）。
    """
    if key in TONE_PROFILES:
        return {**TONE_PROFILES[key], "scenario": key}
    canonical = _canonical(key)
    return {**TONE_PROFILES.get(canonical, TONE_PROFILES[DEFAULT_SCENARIO]), "scenario": canonical}


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

