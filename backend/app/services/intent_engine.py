"""
意图识别：功能 × 维度（不解析企业名）

功能：score / authenticity / fraud / benchmark / trend / report / email_report / signal / general
维度：overall / industry / region / time / signal
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FUNCTIONS = (
    "score",
    "authenticity",
    "fraud",
    "benchmark",
    "trend",
    "report",
    "email_report",
    "custom_report",
    "signal",
    "general",
)
DIMENSIONS = ("overall", "industry", "region", "time", "signal")

_INDUSTRY_KW: list[tuple[str, str]] = [
    ("电子信息", "制造"),
    ("制造", "制造"),
    ("批发", "批发零售"),
    ("零售", "批发零售"),
    ("服务", "服务"),
    ("建筑", "建筑"),
    ("软件", "IT软件"),
    ("信息", "IT软件"),
    ("科技", "IT软件"),
    ("it软件", "IT软件"),
    ("新能源", "新能源"),
    ("医药", "医药"),
    ("生物", "医药"),
    ("餐饮", "餐饮"),
    ("金融", "金融"),
    ("交通", "交通运输"),
    ("运输", "交通运输"),
    ("物流", "交通运输"),
    # 英文别名（BUG-05：英文行业提问也能命中）
    ("manufacturing", "制造"),
    ("retail", "批发零售"),
    ("wholesale", "批发零售"),
    ("construction", "建筑"),
    ("software", "IT软件"),
    ("service", "服务"),
    ("finance", "金融"),
    ("logistics", "交通运输"),
]

_FUNC_PATTERNS: list[tuple[str, list[str]]] = [
    ("email_report", [r"发邮", r"邮件", r"email", r"发送报告", r"发到.*邮箱"]),
    # 「定制报告/定制/自定义」优先于 report（report 的「报告」会抢走「定制报告」）
    ("custom_report", [r"定制报告", r"定制", r"自定义报告", r"自定义", r"AI定制", r"帮我定制"]),
    ("report", [r"报告", r"出报告", r"生成报告", r"pdf", r"导出", r"评估报告", r"\breport\b"]),
    ("authenticity", [r"真伪", r"真实性", r"造假", r"虚开", r"benford", r"可信度", r"经营真实", r"authenticity", r"verification"]),
    ("fraud", [r"舞弊", r"欺诈", r"发票异常", r"红冲", r"集中度", r"异常检测", r"进销错配", r"\bfraud\b", r"anomaly", r"mismatch"]),
    ("benchmark", [r"对标", r"同业", r"行业对比", r"基准", r"percentile", r"[跟和与]同行", r"benchmark", r"\bpeer\b", r"comparison"]),
    ("trend", [r"趋势", r"走向", r"同比", r"环比", r"变化", r"走势", r"\btrend\b", r"yoy", r"mom"]),
    ("score", [r"评分", r"风险分(?!布)", r"打分", r"综合分", r"风险等级", r"税务健康", r"纳税", r"\bscore\b", r"rating", r"credit score"]),
    ("signal", [r"预警", r"信号", r"告警", r"风险点", r"风险预警", r"风险分布", r"\bwarning\b", r"\bsignal\b", r"\balert\b"]),
]

_DIM_PATTERNS: list[tuple[str, list[str]]] = [
    ("signal", [r"预警", r"信号", r"告警", r"风险点", r"\bsignal\b", r"warning", r"alert"]),
    ("region", [r"地区", r"区域", r"省份", r"省市", r"地域", r"region", r"province"]),
    ("time", [r"时间", r"月份", r"季度", r"年度", r"近期", r"month", r"quarter", r"\byear\b"]),
    ("industry", [r"行业", r"产业", r"各业", r"分行业", r"同行", r"industry", r"sector"]),
]

_PROVINCE_KW: list[tuple[str, str]] = [
    ("广东", "广东"),
    ("深圳", "广东"),
    ("上海", "上海"),
    ("北京", "北京"),
    ("浙江", "浙江"),
    ("江苏", "江苏"),
    ("四川", "四川"),
    ("山东", "山东"),
    ("河南", "河南"),
    ("湖北", "湖北"),
    ("湖南", "湖南"),
    ("福建", "福建"),
    ("安徽", "安徽"),
    ("河北", "河北"),
    ("陕西", "陕西"),
    ("重庆", "重庆"),
    ("天津", "天津"),
    ("江西", "江西"),
    ("山西", "山西"),
    ("辽宁", "辽宁"),
    ("吉林", "吉林"),
    ("黑龙江", "黑龙江"),
    ("海南", "海南"),
    ("贵州", "贵州"),
    ("云南", "云南"),
    ("甘肃", "甘肃"),
    ("青海", "青海"),
    ("内蒙古", "内蒙古"),
    ("广西", "广西"),
    ("西藏", "西藏"),
    ("宁夏", "宁夏"),
    ("新疆", "新疆"),
    ("香港", "香港"),
    ("澳门", "澳门"),
]

# 旧意图别名 → (function, dimension)
_LEGACY_MAP = {
    "tax_health": ("score", "overall"),
    "industry_compare": ("benchmark", "industry"),
    "enterprise_pk": ("benchmark", "industry"),
    "risk_warning": ("signal", "signal"),
    "full_report": ("report", "overall"),
    "chat": ("general", "overall"),
}

FOLLOWUP_RE = re.compile(r"^(它|他|她|这个|那个|那|那么|还有|继续|呢|怎么样|如何)|\b呢\b|方面呢|呢[？?]?$")

TEST_CASES: list[tuple[str, str]] = [
    ("分析各行业的趋势走向", "trend"),
    ("看经营真实性", "authenticity"),
    ("发票舞弊异常检测", "fraud"),
    ("跟同行对标", "benchmark"),
    ("税务健康评分", "score"),
    ("有哪些风险预警", "signal"),
    ("生成评估报告", "report"),
    ("把报告发到邮箱", "email_report"),
    ("各地区信用分对比", "score"),
    ("广东地区信用分对比", "score"),
    ("按地区分析风险分布", "score"),
    ("制造业营收趋势", "trend"),
    ("你好", "general"),
]


@dataclass
class IntentResult:
    function: str = "general"
    dimension: str = "overall"
    industry_l1: str | None = None
    province: str | None = None
    confidence: float = 0.5
    raw_query: str = ""
    intent: str = "general"
    entity_name: str | None = None
    entity_id: str | None = None
    # 兼容旧 chat_router / 测试
    enterprises: list[str] = field(default_factory=list)
    enterprise_names: list[str] = field(default_factory=list)
    recipient: str | None = None
    extras: dict = field(default_factory=dict)
    # 语义中间表示（P0 新增，非破坏）：LLM 结构化解析结果或规则转换结果
    semantic_query: "SemanticQuery | None" = None

    @property
    def route_key(self) -> str:
        return f"{self.function}:{self.dimension}"


def _match_function(q: str) -> tuple[str, float]:
    for name, pats in _FUNC_PATTERNS:
        for p in pats:
            if re.search(p, q, re.I):
                return name, 0.85
    return "general", 0.4


def _match_dimension(q: str, function: str) -> tuple[str, float]:
    for name, pats in _DIM_PATTERNS:
        for p in pats:
            if re.search(p, q, re.I):
                return name, 0.8
    if function in ("trend", "benchmark"):
        return "industry", 0.55
    if function == "signal":
        return "signal", 0.7
    if function == "report":
        return "overall", 0.55
    if "各" in q or "整体" in q or "全部" in q:
        return "industry", 0.6
    return "overall", 0.45


def industry_l1_options() -> list[str]:
    """去重后的行业大类列表（供 LLM 白名单与测试）。"""
    seen: list[str] = []
    for _, ind in _INDUSTRY_KW:
        if ind not in seen:
            seen.append(ind)
    return seen


def province_options() -> list[str]:
    """去重后的地区白名单（供 LLM 定制对话槽位约束）。"""
    seen: list[str] = []
    for _, prov in _PROVINCE_KW:
        if prov not in seen:
            seen.append(prov)
    return seen


def _match_industry(q: str) -> str | None:
    ql = q.lower()
    if re.search(r"\bit\b", ql) or "it软件" in ql.replace(" ", ""):
        return "IT软件"
    for kw, ind in _INDUSTRY_KW:
        if kw.lower() in ql:
            return ind
    return None


def _match_province(q: str) -> str | None:
    for kw, prov in _PROVINCE_KW:
        if kw in q:
            return prov
    return None


def _extract_email(q: str) -> str | None:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", q)
    return m.group(0) if m else None


def parse_intent(query: str, session_context: dict | None = None) -> IntentResult:
    q = (query or "").strip()
    if not q:
        return IntentResult(raw_query=q)

    # 追问：默认继承上一轮 function；若句内显式出现功能词则切换
    if session_context and is_followup_query(q):
        explicit_fn, _ = _match_function(q)
        if explicit_fn != "general":
            function = explicit_fn
        else:
            last_fn = session_context.get("last_function") or session_context.get("last_intent")
            if last_fn and "_" in str(last_fn):
                last_fn = str(last_fn).split("_")[0]
            function = last_fn if last_fn in FUNCTIONS and last_fn != "general" else "general"
        if function in FUNCTIONS and function != "general":
            dimension, dc = _match_dimension(q, function)
            industry = _match_industry(q) or session_context.get("industry_l1")
            province = _match_province(q) or session_context.get("province")
            switched_province = bool(_match_province(q))
            switched_industry = bool(_match_industry(q))
            # 追问切换省份/行业时补全维度，便于下钻过滤
            if switched_province and dimension == "overall":
                dimension = "region"
            if switched_industry and dimension == "overall" and function in (
                "trend",
                "benchmark",
                "score",
                "authenticity",
                "fraud",
            ):
                dimension = "industry"
            return IntentResult(
                function=function,
                dimension=dimension,
                industry_l1=industry,
                province=province,
                confidence=0.75 if explicit_fn != "general" else 0.7,
                raw_query=q,
                intent=f"{function}_{dimension}",
                recipient=_extract_email(q),
                extras={
                    "followup": True,
                    "switched_function": explicit_fn != "general",
                    "switched_province": switched_province,
                    "switched_industry": switched_industry,
                },
            )

    function, fc = _match_function(q)
    dimension, dc = _match_dimension(q, function)
    industry = _match_industry(q)
    province = _match_province(q)

    # 区域/地区提问：默认做地区间评分对比（具备对比图），而非落入 general/signal
    if dimension == "region" and function in ("general", "signal"):
        function = "score"
        fc = 0.7

    if re.search(r"趋势|走向|走势", q) and re.search(r"行业|各业", q):
        function, dimension = "trend", "industry"
        fc, dc = 0.95, 0.95

    # 风险信号 + 行业/区域：保留行业/区域维度，不强制 signal/signal
    if function == "signal" and dimension in ("overall", "signal"):
        dimension = "signal"

    conf = min(0.98, (fc + dc) / 2 + 0.1)
    intent = f"{function}_{dimension}"
    return IntentResult(
        function=function,
        dimension=dimension,
        industry_l1=industry,
        province=province,
        confidence=conf,
        raw_query=q,
        intent=intent,
        recipient=_extract_email(q),
        extras={"matched_industry": industry},
    )


async def parse_intent_async(query: str, history: list | None = None) -> IntentResult:
    return parse_intent(query)


def recognize(query: str, session_context: dict | None = None) -> IntentResult:
    """规则意图识别；发散问法 LLM 兜底见 chat_router.route_chat。"""
    return parse_intent(query, session_context=session_context)


def _match_intent_rules(query: str) -> tuple[str, list[str]]:
    """返回 (function, keywords) — 测试用。"""
    r = parse_intent(query)
    kws = [w for w in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]+", query)]
    return r.function, kws


def extract_enterprises(query: str) -> tuple[list[str], list[str]]:
    """匿名模式：仅匹配 ENT 风格 ID，不解析具名企业。"""
    ids = re.findall(r"ENT\d+", query or "", flags=re.I)
    return ([i.upper() for i in ids], [])


def is_followup_query(query: str) -> bool:
    q = (query or "").strip()
    if len(q) <= 8 and FOLLOWUP_RE.search(q):
        return True
    if re.search(r"(方面呢|呢[？?]?$|那.+呢)", q) and len(q) < 20:
        return True
    return False


def _normalize_intent(intent: str) -> str:
    if intent == "chat":
        return "general"
    if intent in _LEGACY_MAP:
        return intent
    if intent in FUNCTIONS:
        return intent
    if "_" in intent:
        return intent.split("_")[0]
    return intent or "general"


def evaluate() -> dict:
    ok = 0
    details = []
    for q, expect_fn in TEST_CASES:
        r = recognize(q)
        hit = r.function == expect_fn
        ok += int(hit)
        details.append({"query": q, "expected": expect_fn, "got": r.function, "ok": hit})
    acc = round(100.0 * ok / max(len(TEST_CASES), 1), 2)
    return {"accuracy": acc, "total": len(TEST_CASES), "correct": ok, "details": details}


def resolve_entity(name: str) -> tuple[str | None, str | None]:
    return None, None
