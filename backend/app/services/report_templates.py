"""报告场景模板：五场景 × (维度×功能) 章节装配规则（L3 结构层）。

五场景对齐产品「财税票多源数据」四大数据类：
- 财务健康体检（财务数据）
- 税务合规体检（税务数据）
- 发票舞弊排查（发票数据）
- 企业画像（企业基础信息）
- 综合尽调（四类全覆盖，默认）

同一批数据，按输入偏好落到不同场景 → 不同章节侧重/顺序/封面母题。
数据与评级永远来自 L0/L1（铁律），此处只决定「结构 + 语气」的差异化（L2/L3）。
"""
from __future__ import annotations

import os
from typing import Any

# 每章：功能是什么 → 由 judgment 填结论 → 证据链来自 claim.trace
ChapterSpec = dict[str, Any]

# 场景封面母题（前端据此渲染不同图形）+ 主色（品牌藏蓝为底，每场景一个强调色）
# motif 取值：ledger / seal / magnifier / compass / badge
SCENARIOS: dict[str, dict[str, Any]] = {
    "financial": {
        "title": "财务健康体检报告",
        "subtitle": "盈利能力 · 偿债能力 · 营运能力 · 现金流",
        "tier": "general",
        "story": "以财务四大能力为主线，结合营收趋势与同业基准，判断财务稳健度与偿债压力。",
        "data_focus": ["财务数据", "企业基础信息"],
        "cover": {"motif": "ledger", "accent": "#0f766e"},
        "kpis": [
            {"label": "毛利率", "metric": "gross_margin", "unit": "%", "source": "enterprise_financials"},
            {"label": "净利率", "metric": "net_margin", "unit": "%", "source": "enterprise_financials"},
            {"label": "资产负债率", "metric": "debt_ratio", "unit": "%", "source": "core_metrics"},
            {"label": "经营现金流", "metric": "operating_cf", "unit": "元", "source": "enterprise_financials"},
        ],
        "chapters": [
            {
                "function": "financial",
                "dimension": "overall",
                "title": "财务四能力健康度",
                "purpose": "偿债/营运/盈利/成长四能力比率均值与客观评级（阈值统一）。",
            },
            {
                "function": "authenticity",
                "dimension": "overall",
                "title": "财务勾稽与真实性",
                "purpose": "多源营收偏差与利润累计额 Benford 检验，评估财务数据质量。",
            },
            {
                "function": "benchmark",
                "dimension": "industry",
                "title": "财务同业对标",
                "purpose": "行业均值与财务基准对照，定位样本在同业中的分位。",
            },
            {
                "function": "trend",
                "dimension": "industry",
                "title": "营收趋势",
                "purpose": "各行业大类营收同比与社保趋势，刻画上行/平稳/下行。",
            },
        ],
    },
    "tax": {
        "title": "税务合规体检报告",
        "subtitle": "税负水平 · 欠税风险 · 申报准时率",
        "tier": "general",
        "story": "围绕税务合规度，聚焦纳税准时率、税务违法信号与税负水平，识别补税与滞纳风险。",
        "data_focus": ["税务数据", "企业基础信息"],
        "cover": {"motif": "seal", "accent": "#1d4ed8"},
        "kpis": [
            {"label": "纳税准时率", "metric": "tax_on_time_rate", "unit": "%", "source": "core_metrics"},
            {"label": "增值税税负", "metric": "vat_burden", "unit": "%", "source": "core_metrics"},
            {"label": "所得税税负", "metric": "income_tax_burden", "unit": "%", "source": "core_metrics"},
            {"label": "滞纳/处罚次数", "metric": "tax_late_penalty_cnt", "unit": "次", "source": "core_metrics"},
        ],
        "chapters": [
            {
                "function": "tax",
                "dimension": "overall",
                "title": "税务合规概览",
                "purpose": "纳税准时率、增值税/所得税税负、欠税与违法主体计数。",
            },
            {
                "function": "signal",
                "dimension": "signal",
                "title": "税务风险信号",
                "purpose": "汇总欠税、滞纳、税务违法等信号的切片分布。",
            },
            {
                "function": "score",
                "dimension": "industry",
                "title": "纳税信用与准时率",
                "purpose": "按行业汇总纳税准时率与信用分，识别合规洼地。",
            },
            {
                "function": "authenticity",
                "dimension": "overall",
                "title": "税务-财报勾稽",
                "purpose": "税务口径与财报口径偏差交叉验证。",
            },
        ],
    },
    "fraud": {
        "title": "发票舞弊排查报告",
        "subtitle": "进销错配 · 红冲异常 · 集中度风险",
        "tier": "general",
        "story": "聚焦发票明细异常，覆盖进销错配、红字发票、集中度与序列缺口，定位可疑开票主体。",
        "data_focus": ["发票数据", "企业基础信息"],
        "cover": {"motif": "magnifier", "accent": "#d32f2f"},
        "kpis": [
            {"label": "舞弊信号数", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
            {"label": "可疑主体占比", "metric": "suspicious_ratio", "unit": "%", "source": "fraud"},
            {"label": "进销错配主体占比", "metric": "scbm_mismatch_rate", "unit": "%", "source": "fraud"},
            {"label": "红字异常主体占比", "metric": "red_anomaly_ratio", "unit": "%", "source": "fraud"},
        ],
        "chapters": [
            {
                "function": "fraud",
                "dimension": "industry",
                "title": "发票舞弊切片",
                "purpose": "基于发票明细的进销错配、红字、集中度与序列缺口。",
            },
            {
                "function": "authenticity",
                "dimension": "overall",
                "title": "真实性交叉验证",
                "purpose": "增值税/发票/财报口径偏差与 Benford 检验。",
            },
            {
                "function": "signal",
                "dimension": "signal",
                "title": "风险信号",
                "purpose": "税务违法、营收高偏差与低信用主体在行业中的集中情况。",
            },
        ],
    },
    "due_diligence": {
        "title": "综合尽调报告",
        "subtitle": "综合评分 · 经营真实性 · 舞弊 · 同业对标",
        "tier": "general",
        "story": "尽调视角一站式覆盖综合评分、经营真实性、发票舞弊与同业对标，输出全维度风险结论。",
        "data_focus": ["财务数据", "税务数据", "发票数据", "企业基础信息"],
        "cover": {"motif": "compass", "accent": "#003366"},
        "kpis": [
            {"label": "综合评分", "metric": "overall_score", "unit": "分", "source": "assessment"},
            {"label": "风险等级", "metric": "risk_level", "unit": "档", "source": "computed"},
            {"label": "预警主体数", "metric": "flagged_count", "unit": "家", "source": "core_metrics"},
            {"label": "同业分位", "metric": "benchmark_percentile", "unit": "%", "source": "industry_benchmark"},
        ],
        "chapters": [
            {"function": "score", "dimension": "industry", "title": "综合评分切片", "purpose": "行业信用与纳税健康。"},
            {"function": "authenticity", "dimension": "overall", "title": "经营真实性", "purpose": "交叉验证与 Benford。"},
            {"function": "fraud", "dimension": "overall", "title": "发票舞弊检测", "purpose": "发票异常信号汇总。"},
            {"function": "benchmark", "dimension": "industry", "title": "行业对标", "purpose": "industry_benchmark 基准对照。"},
            {"function": "signal", "dimension": "signal", "title": "预警清单", "purpose": "高风险信号计数。"},
        ],
    },
    "profile": {
        "title": "企业画像报告",
        "subtitle": "规模 · 地区 · 行业 · 信用等级",
        "tier": "general",
        "story": "以企业基础信息为主线，刻画样本的规模、地区、行业分布与信用等级结构，建立总体认知。",
        "data_focus": ["企业基础信息"],
        "cover": {"motif": "badge", "accent": "#6d28d9"},
        "kpis": [
            {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
            {"label": "覆盖地区", "metric": "region_count", "unit": "个", "source": "core_metrics"},
            {"label": "覆盖行业", "metric": "industry_count", "unit": "个", "source": "core_metrics"},
            {"label": "信用等级", "metric": "credit_grade", "unit": "级", "source": "core_metrics"},
        ],
        "chapters": [
            {
                "function": "score",
                "dimension": "region",
                "title": "地区信用画像",
                "purpose": "分省份信用分对比与极差，刻画地区风险梯度。",
            },
            {
                "function": "trend",
                "dimension": "industry",
                "title": "行业规模画像",
                "purpose": "行业营收规模与主体数量分布，定位样本结构。",
            },
            {
                "function": "benchmark",
                "dimension": "industry",
                "title": "行业基准定位",
                "purpose": "样本均值 vs 行业基准，识别偏离行业。",
            },
            {
                "function": "signal",
                "dimension": "signal",
                "title": "信用等级分布",
                "purpose": "高低信用等级主体分布与高风险集中情况。",
            },
        ],
    },
    "overview": {
        "title": "综合总览报告",
        "subtitle": "六维画像 · 信号总览 · 五场景摘要索引",
        "tier": "general",
        "story": "汇总全样本六维画像与风险信号总览，并为五套专项切片提供摘要索引，形成一站式总览。",
        "data_focus": ["财务数据", "税务数据", "发票数据", "企业基础信息"],
        "cover": {"motif": "compass", "accent": "#003366"},
        "kpis": [
            {"label": "综合评分", "metric": "overall_score", "unit": "分", "source": "assessment"},
            {"label": "风险等级", "metric": "risk_level", "unit": "档", "source": "computed"},
            {"label": "预警主体数", "metric": "flagged_count", "unit": "家", "source": "core_metrics"},
            {"label": "样本规模", "metric": "sample_count", "unit": "家", "source": "core_metrics"},
        ],
        "chapters": [
            {"function": "score", "dimension": "overall", "title": "六维综合画像", "purpose": "样本六维均分雷达与综合均分。"},
            {"function": "signal", "dimension": "signal", "title": "风险信号总览", "purpose": "预警信号分布与多重风险叠加主体计数。"},
            {"function": "financial", "dimension": "overall", "title": "财务健康摘要", "purpose": "四能力比率均值与客观评级摘要。"},
            {"function": "tax", "dimension": "overall", "title": "税务合规摘要", "purpose": "纳税准时率、税负与违法信号摘要。"},
            {"function": "fraud", "dimension": "overall", "title": "发票舞弊摘要", "purpose": "进销错配、红冲、集中度与序列缺口摘要。"},
            {"function": "authenticity", "dimension": "overall", "title": "经营真实性摘要", "purpose": "多源营收偏差与 Benford 检验摘要。"},
        ],
    },
}

# 场景中文名（含数据类侧重提示）
SCENARIO_LABELS = {
    "financial": "财务健康体检（财务数据）",
    "tax": "税务合规体检（税务数据）",
    "fraud": "发票舞弊排查（发票数据）",
    "due_diligence": "综合尽调（四类全覆盖）",
    "profile": "企业画像（基础信息）",
    "overview": "综合总览（五场景摘要索引）",
    "custom": "定制风控报告（对话式自由组合）",
}

# ── 定制报告：可自由组合的章节词汇（L3 结构层）──
# AI 定制对话把用户诉求映射为 8 个可组合「功能」的有序子集，逐个复用既有章节 builder。
# value = (章节标题, 章节说明)。key 与 judgment_service 的 8 个 function 一一对应。
CUSTOM_CHAPTERS: dict[str, tuple[str, str]] = {
    "financial": ("财务健康", "财务四能力 + 勾稽真实性 + 同业对标"),
    "tax": ("税务合规", "税负 + 纳税准时率 + 欠税信号"),
    "fraud": ("发票舞弊", "进销错配/红冲/集中度/序列缺口"),
    "authenticity": ("经营真实性", "Benford + 多源勾稽一致性"),
    "signal": ("风险信号总览", "违法/偏差/信用/多重叠加"),
    "score": ("六维综合评分", "六维加权评分与归因"),
    "benchmark": ("行业对标", "同行均值/百分位"),
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
    "financial": {
        "persona": "资深财务分析师",
        "style": "简洁克制，紧扣数字含义与偿债/盈利压力，多用短句，不渲染。",
    },
    "tax": {
        "persona": "税务合规顾问",
        "style": "谨慎专业，突出合规风险、补税与滞纳后果，结论留有余地。",
    },
    "fraud": {
        "persona": "反舞弊调查员",
        "style": "直接警觉，聚焦异常证据与可疑主体，只陈述证据不妄下结论。",
    },
    "due_diligence": {
        "persona": "尽调分析师",
        "style": "全面客观，风险分级清晰，结论可执行、可回溯。",
    },
    "profile": {
        "persona": "数据分析师",
        "style": "中性结构化，重分布与占比，不渲染情绪。",
    },
    "overview": {
        "persona": "风控总览分析师",
        "style": "总览中立，跨场景摘要并置，突出关键风险与索引，不渲染情绪。",
    },
    "enterprise": {
        "persona": "财务分析师",
        "style": "针对单个主体做深度判断，点明风险点与建议。",
    },
    "custom": {
        "persona": "风控定制顾问",
        "style": "中性克制，紧扣用户定制诉求组织章节，结论与评级仍由引擎统一给出，不渲染情绪。",
    },
}

# 去 AI 味：统一禁用套话/过渡词（各场景共用，避免「AI 腔」）
BANNED_AI_PHRASES = (
    "首先，其次，再次，最后，综上所述，总而言之，总的说来，值得注意的是，"
    "由此可见，不难发现，作为一个，需要指出的是，换言之，换句话说，"
    "在这个背景下，随着，可以说，总的来说，接下来，基于上述分析"
)


# 对话快捷：「生成报告」默认综合尽调；可指定场景关键词
SCENARIO_ALIASES = {
    "财务": "financial",
    "财务健康": "financial",
    "盈利": "financial",
    "偿债": "financial",
    "现金流": "financial",
    "税务": "tax",
    "合规": "tax",
    "税负": "tax",
    "欠税": "tax",
    "纳税": "tax",
    "发票": "fraud",
    "舞弊": "fraud",
    "欺诈": "fraud",
    "红冲": "fraud",
    "进销": "fraud",
    "尽调": "due_diligence",
    "综合": "due_diligence",
    "全面": "due_diligence",
    "画像": "profile",
    "基础信息": "profile",
    "企业概况": "profile",
    "概览": "profile",
    "基本面": "financial",
    "趋势": "due_diligence",
    "通识": "due_diligence",
    "总览": "overview",
    "汇总": "overview",
    "综合总览": "overview",
}

# 旧场景 key → 新场景 key（兼容历史文件名 slice_general_*、旧 API 显式 scenario）
_LEGACY_SCENARIO_MAP = {
    "general": "due_diligence",
    "fundamental": "financial",
    "custom": "due_diligence",
}

DEFAULT_SCENARIO = "due_diligence"


def _canonical(key: str | None) -> str:
    """旧 key 归一化到新五场景，未知 key 保持原样（调用方决定是否报错）。"""
    if not key:
        return DEFAULT_SCENARIO
    return _LEGACY_SCENARIO_MAP.get(key, key)


def has_scenario_keyword(query: str | None) -> bool:
    """query 是否显式命中某个场景关键词（用于区分「生成报告」=罗列路径 vs 指定场景=直接生成）。"""
    q = query or ""
    return any(kw in q for kw in SCENARIO_ALIASES)


def scenario_path_prompts() -> list[str]:
    """罗列生成路径（供对话引导用户选择）。"""
    return [
        f"生成{SCENARIOS[k]['title']}"
        for k in ("financial", "tax", "fraud", "due_diligence", "profile", "overview")
    ]


def resolve_scenario(query: str | None = None, scenario: str | None = None) -> str:
    if scenario:
        key = _canonical(scenario)
        if key in SCENARIOS:
            return key
        # 显式传入未知 scenario 时不再静默回退，便于调用方发现拼写错误
        raise ValueError(f"未知报告场景: {scenario}；可选: {', '.join(sorted(SCENARIOS))}")
    q = query or ""
    # 更具体的别名优先（如「综合总览」须先于「综合」命中，否则被归到 due_diligence）。
    for kw, key in sorted(SCENARIO_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if kw in q:
            return key
    return DEFAULT_SCENARIO


def get_scenario(key: str) -> dict[str, Any]:
    return SCENARIOS.get(_canonical(key)) or SCENARIOS[DEFAULT_SCENARIO]


def get_scenario_tier(key: str) -> str:
    """通用模板 general（免费） vs 定制 premium（付费）。五场景均为 general。"""
    return (SCENARIOS.get(_canonical(key)) or SCENARIOS[DEFAULT_SCENARIO]).get("tier", "general")


def get_scenario_label(key: str) -> str:
    return SCENARIO_LABELS.get(key) or SCENARIO_LABELS.get(_canonical(key), key)


def scope_label(industry_l1: str | None = None, province: str | None = None) -> str:
    """范围前缀（行业/地区），用于报告标题；无范围返回空串。"""
    return industry_l1 or province or ""


def get_scenario_cover(key: str) -> dict[str, str]:
    """场景封面母题 + 主色，供封面图形渲染（L4）。"""
    spec = SCENARIOS.get(_canonical(key)) or SCENARIOS[DEFAULT_SCENARIO]
    return dict(spec.get("cover") or {"motif": "compass", "accent": "#003366"})


def get_scenario_tone(key: str) -> dict[str, str]:
    """场景语气（L2）：报告解读/摘要的身份与文风；未知 key 回退综合尽调。"""
    if key in TONE_PROFILES:
        return TONE_PROFILES[key]
    return TONE_PROFILES.get(_canonical(key), TONE_PROFILES[DEFAULT_SCENARIO])


class PremiumReportLocked(Exception):
    """定制报告（付费层级）在开发期被隔离，尚未开放。"""


def is_premium_locked() -> bool:
    """开发期付费隔离开关。

    默认锁定（false）：premium 场景仅展示层级、不产出报告。
    上线后置 ``PREMIUM_REPORT_ENABLED=true`` 即可开放付费定制链路。
    """
    return os.getenv("PREMIUM_REPORT_ENABLED", "false").lower() not in ("1", "true", "yes")


# ── 术语词典（附录）：把指标/算法黑话翻译成平实中文，便于非技术读者回溯结论 ──
GLOSSARY: list[dict[str, str]] = [
    {"term": "scbm_mismatch", "def": "进销项「商品编码」不一致，通常提示买卖品目对不上。"},
    {"term": "red_invoice", "def": "红字（负数）发票，即冲销原发票；频繁冲红提示开票异常。"},
    {"term": "concentration", "def": "客户/供应商/品目集中度；占比过高意味着对单一对手方依赖过重。"},
    {"term": "sequence_gap", "def": "发票号码序列缺口，可能提示批量作废、跳号或人为操控。"},
    {"term": "Benford χ²/MAD", "def": "数字首位数分布检验；χ² 与 MAD 偏离理论分布越远，越像人为编造。"},
    {"term": "六维加权贡献", "def": "六个风控维度按权重对综合评分的拉动（正为加分、负为扣分）。"},
    {"term": "cross_avg_deviation", "def": "同一主体的税务、发票、财报三口径营收相互之间的平均偏差。"},
    {"term": "pyod IForest", "def": "孤立森林无监督异常检测，度量主体偏离正常群的程度。"},
    {"term": "风险等级", "def": "综合评分分档：≥80 低风险 / ≥65 中低风险 / ≥50 中等风险 / ≥35 中高风险 / 其余 高风险。"},
    {"term": "评级展望", "def": "风险走向判断：负面（高危事件或高风险/中高风险等级）/ 正面（低风险，或营收与净利润同比均为正）/ 稳定（其余，趋势缺失弃权）。"},
]


def build_glossary() -> list[dict[str, str]]:
    """术语词典（附录用），静态、无数字结论。"""
    return [dict(row) for row in GLOSSARY]
