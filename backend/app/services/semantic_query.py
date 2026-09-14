"""SemanticQuery 校正器 / 转换器（纯函数，无 DB、无 LLM）。

职责：
- 把规则意图 IntentResult → SemanticQuery（无 LLM 兜底路径）；
- 把 LLM 解析结果钳制/补全到规范词汇（metrics / dimensions / filters / 默认值）；
- 追问（CQR）时从上一轮 SemanticQuery 继承槽位、覆盖显式声明槽位；
- query_type ↔ function / dimension 互映射（供合成 / 追问 / 持久化）。
"""
from __future__ import annotations

import re
from typing import Any

from app.schemas.semantic_query import CompareTarget, QueryType, SemanticQuery, SortSpec

# 规范 metric 别名（中文口语 → canonical key）
METRIC_ALIASES: dict[str, str] = {
    "信用分": "credit_score",
    "纳税信用分": "credit_score",
    "信用评分": "credit_score",
    "综合评分": "overall_score",
    "综合分": "overall_score",
    "风险分": "overall_score",
    "风险得分": "overall_score",
    "评分": "overall_score",
    "真实性": "authenticity_score",
    "经营真实性": "authenticity_score",
    "真实性得分": "authenticity_score",
    "舞弊": "fraud_composite_score",
    "舞弊分": "fraud_composite_score",
    "欺诈": "fraud_composite_score",
    "营收同比": "revenue_yoy",
    "同比": "revenue_yoy",
    "营收增速": "revenue_yoy",
    "利润率": "profit_margin",
    "纳税准时率": "tax_on_time_rate",
    "营收偏差": "revenue_deviation",
    "客户集中度": "customer_concentration",
    "客户集中": "customer_concentration",
    "供应商集中度": "supplier_concentration",
    "供应商集中": "supplier_concentration",
    "品目集中度": "category_concentration",
    "品目集中": "category_concentration",
    "品类集中度": "category_concentration",
    "增值税税负率": "vat_burden",
    "税负率": "vat_burden",
    "增值税税负": "vat_burden",
    "所得税税负率": "income_tax_burden",
    "所得税税负": "income_tax_burden",
    "申报更正次数": "correction_times",
    "更正次数": "correction_times",
    "社保人数": "social_headcount",
    "社保缴费人数": "social_headcount",
    "滞纳金笔数": "tax_late_penalty_cnt",
    "罚款笔数": "tax_late_penalty_cnt",
    "作废发票": "void_invoice_cnt",
    "作废发票笔数": "void_invoice_cnt",
    "单价离散": "unit_price_ratio",
    "单价离散度": "unit_price_ratio",
    "变更登记次数": "change_cnt",
    "变更次数": "change_cnt",
    "工商变更": "change_cnt",
}

# 维度别名（中文 → 规范维度）
DIMENSION_ALIASES: dict[str, str] = {
    "行业": "industry_l1",
    "产业": "industry_l1",
    "地区": "province",
    "区域": "province",
    "省份": "province",
    "省": "province",
    "规模": "scale_label",
    "时间": "time",
}

# 运行时可表达的非规范 metric（除 canonical 外允许的）
RUNTIME_METRIC_KEYS = frozenset({"fraud_composite_score", "signal_total", "risk_level"})

_GROUP_DIMENSIONS = ("industry_l1", "province", "scale_label", "time")


def canonical_metric_keys() -> list[str]:
    from app.services.metric_registry import CANONICAL_METRICS

    return [m["metric_key"] for m in CANONICAL_METRICS]


def allowed_metrics() -> list[str]:
    """LLM 白名单：规范指标 + 可表达的运行时指标。"""
    return sorted(set(canonical_metric_keys()) | set(RUNTIME_METRIC_KEYS))


def _clamp_metric(value: str) -> str | None:
    key = (value or "").strip().lower()
    if not key:
        return None
    if key in METRIC_ALIASES:
        key = METRIC_ALIASES[key]
    allowed = set(allowed_metrics())
    if key in allowed:
        return key
    # 直接给中文名再试一次
    if value.strip() in METRIC_ALIASES:
        return METRIC_ALIASES[value.strip()]
    return None


def _clamp_dimension(value: str) -> str | None:
    key = (value or "").strip().lower()
    if not key:
        return None
    if key in DIMENSION_ALIASES:
        key = DIMENSION_ALIASES[key]
    if key in _GROUP_DIMENSIONS:
        return key
    if value.strip() in DIMENSION_ALIASES:
        return DIMENSION_ALIASES[value.strip()]
    return None


def _clamp_industry(value: str) -> str | None:
    from app.services.intent_engine import _match_industry

    v = (value or "").strip()
    if not v:
        return None
    return _match_industry(v) or None


def _clamp_province(value: str) -> str | None:
    from app.services.intent_engine import _match_province

    v = (value or "").strip()
    if not v:
        return None
    return _match_province(v) or None


def _default_metric(sq: SemanticQuery) -> str:
    if sq.query_type == QueryType.trend:
        return "revenue_yoy"
    if sq.query_type == QueryType.distribution:
        return "signal_total"
    if sq.dimensions:
        return "credit_score"
    return "overall_score"


def correct_semantic_query(sq: SemanticQuery, session_context: dict | None = None) -> SemanticQuery:
    """钳制/补全槽位：metrics/dimensions 收敛到规范词汇，filters 对齐规范值，补默认 metric。"""
    out = sq.model_copy(deep=True)
    metrics: list[str] = []
    for m in sq.metrics or []:
        key = _clamp_metric(m)
        if key and key not in metrics:
            metrics.append(key)
    out.metrics = metrics

    dims: list[str] = []
    for d in sq.dimensions or []:
        key = _clamp_dimension(d)
        if key and key not in dims:
            dims.append(key)
    out.dimensions = dims

    filters: dict[str, list[str]] = {}
    for k, values in (sq.filters or {}).items():
        dk = _clamp_dimension(k)
        if not dk:
            continue
        clamped: list[str] = []
        for v in values or []:
            if dk == "industry_l1":
                cv = _clamp_industry(v)
            elif dk == "province":
                cv = _clamp_province(v)
            else:
                cv = (v or "").strip() or None
            if cv and cv not in clamped:
                clamped.append(cv)
        if clamped:
            filters[dk] = clamped
    out.filters = filters

    compare: list[CompareTarget] = []
    for c in sq.compare or []:
        dk = _clamp_dimension(c.dimension) or c.dimension
        values: list[str] = []
        for v in c.values or []:
            if dk == "industry_l1":
                cv = _clamp_industry(v)
            elif dk == "province":
                cv = _clamp_province(v)
            else:
                cv = (v or "").strip() or None
            if cv and cv not in values:
                values.append(cv)
        compare.append(CompareTarget(dimension=dk, values=values))
    out.compare = compare

    # 相关性需恰两个 metric
    if out.query_type == QueryType.correlation and len(out.metrics) < 2:
        if len(out.metrics) == 1:
            out.metrics = out.metrics + [out.metrics[0]]
        else:
            out.metrics = ["credit_score", "revenue_yoy"]

    if not out.metrics:
        out.metrics = [_default_metric(out)]

    if out.sort is not None and not out.sort.metric:
        out.sort = SortSpec(metric=(out.metrics[0] if out.metrics else "overall_score"), order=out.sort.order)

    out.source = "corrected"
    return out


def infer_query_type(intent: Any) -> QueryType:
    fn = getattr(intent, "function", "general")
    dim = getattr(intent, "dimension", "overall")
    if fn == "trend":
        return QueryType.trend
    if fn == "signal" or (fn == "general" and dim == "signal"):
        return QueryType.distribution
    if fn in ("score", "benchmark", "authenticity", "fraud"):
        return QueryType.aggregation
    return QueryType.aggregation


def intent_to_semantic_query(intent: Any) -> SemanticQuery:
    """规则意图 → SemanticQuery（无 LLM 兜底路径，保持既有行为但不产生 'hint' 死胡同）。"""
    fn = getattr(intent, "function", "general")
    dim = getattr(intent, "dimension", "overall")
    qt = infer_query_type(intent)

    metrics: list[str] = []
    dims: list[str] = []
    if fn == "trend":
        metrics = ["revenue_yoy"]
        dims = ["industry_l1"] if dim == "industry" else (["province"] if dim == "region" else [])
    elif fn in ("score", "benchmark"):
        metrics = ["credit_score"] if dim in ("industry", "region") else ["overall_score"]
        dims = {"industry": ["industry_l1"], "region": ["province"]}.get(dim, [])
    elif fn == "authenticity":
        metrics = ["authenticity_score"]
        dims = ["industry_l1"] if dim == "industry" else []
    elif fn == "fraud":
        metrics = ["fraud_composite_score"]
        dims = ["industry_l1"] if dim == "industry" else []
    elif fn == "signal" or (fn == "general" and dim == "signal"):
        metrics = ["signal_total"]
        dims = []
    else:
        metrics = ["credit_score"]
        dims = []

    filters: dict[str, list[str]] = {}
    ind = getattr(intent, "industry_l1", None)
    prov = getattr(intent, "province", None)
    if ind:
        filters["industry_l1"] = [ind]
    if prov:
        filters["province"] = [prov]

    return SemanticQuery(
        query_type=qt,
        metrics=metrics,
        dimensions=dims,
        filters=filters,
        raw_query=getattr(intent, "raw_query", "") or "",
        confidence=getattr(intent, "confidence", 0.5),
        source="rule",
    )


def _first_metric(sq: SemanticQuery) -> str:
    return (sq.metrics or ["overall_score"])[0]


def query_type_to_function(sq: SemanticQuery) -> str:
    qt = sq.query_type
    metric = _first_metric(sq)
    if qt == QueryType.trend:
        return "trend"
    if qt == QueryType.distribution:
        return "signal"
    if qt == QueryType.segmentation:
        if metric == "authenticity_score":
            return "authenticity"
        if metric == "fraud_composite_score":
            return "fraud"
        return "score"
    if qt == QueryType.comparison:
        return "benchmark"
    if qt in (QueryType.lookup, QueryType.aggregation):
        if metric == "authenticity_score":
            return "authenticity"
        if metric == "fraud_composite_score":
            return "fraud"
        if metric == "revenue_yoy":
            return "trend"
        return "score"
    if qt in (QueryType.ranking, QueryType.correlation):
        return "score"
    # faq / methodology：不污染 ANALYSIS_FUNCTIONS 覆盖/综合
    return "general"


def query_type_to_dimension(sq: SemanticQuery) -> str:
    qt = sq.query_type
    if qt == QueryType.distribution:
        return "signal"
    dims = sq.dimensions or []
    if "province" in dims:
        return "region"
    if "industry_l1" in dims:
        return "industry"
    if "scale_label" in dims:
        return "industry"
    if qt == QueryType.trend:
        return "time"
    return "overall"


def _has_explicit_slots(sq: SemanticQuery) -> bool:
    return bool(sq.metrics or sq.dimensions or sq.compare)


# 产品说明/口径问句的显式问句标记（区别于「生成报告」这类祈使指令）。
_QUESTION_MARK_RE = re.compile(
    r"怎么|如何|怎样|为何|为什么|是什么|什么|哪|能否|能不能|可以|能|说明|介绍|用途|功能|几类|哪些|是否"
)


def _looks_like_question(query: str) -> bool:
    return bool(_QUESTION_MARK_RE.search(query or ""))


def detect_faq_or_methodology(query: str) -> SemanticQuery | None:
    """规则层 FAQ / 方法论前置判定（无 LLM 也能命中，先于「报告*」关键词）。

    只对「问句」返回结果：`报告怎么生成`→faq、`综合评分怎么算的`→methodology；
    `生成报告`/`导出报告`这类祈使指令返回 None，交给正常报告意图。
    """
    from app.services.faq_kb import match_faq

    entry = match_faq(query)
    if entry is None or not _looks_like_question(query):
        return None
    if entry["id"] == "method":
        return SemanticQuery(query_type=QueryType.methodology, raw_query=query, source="rule")
    return SemanticQuery(query_type=QueryType.faq, raw_query=query, source="rule")


# 对比问法的显式标记（区别于「对标/跟同行」这类单边 benchmark 问法）。
_COMPARISON_MARK_RE = re.compile(r"对比|比较|相比|差异|谁高|谁低|哪个高|哪个低|高多少|低多少|\bvs\b|VS")


def _rule_comparison_metric(q: str) -> str:
    """对比的默认指标：营收/同比问法取营收同比，否则取信用分（与 build_comparison_claims 默认一致）。"""
    if re.search(r"营收|同比|增速", q):
        return "revenue_yoy"
    return "credit_score"


def _values_in_query_order(q: str, kw_list) -> list[str]:
    """按在查询中的先后顺序取出命中的规范值（去重，保留首次出现位置）。"""
    ql = q.lower()
    pos: dict[str, int] = {}
    for kw, val in kw_list:
        idx = ql.find(kw.lower())
        if idx == -1:
            continue
        if val not in pos or idx < pos[val]:
            pos[val] = idx
    return [val for val, _ in sorted(pos.items(), key=lambda kv: kv[1])]


def detect_rule_comparison(query: str) -> SemanticQuery | None:
    """规则层「对比」前置判定（无 LLM 降级用）：识别「A 和 B 对比/比较」的双省或双行业问法。

    仅当同一维度下能稳定取出 ≥2 个不同值才判定为 comparison，否则返回 None，
    避免把「各地区信用分对比」「跟同行对标」这类单边问法误判成双值对比。
    """
    q = (query or "").strip()
    if not q or not _COMPARISON_MARK_RE.search(q):
        return None

    from app.services.intent_engine import _INDUSTRY_KW, _PROVINCE_KW, _match_industry

    # 双省：取至少两个不同省份（深圳→广东 已合并去重）
    provs = _values_in_query_order(q, _PROVINCE_KW)
    if len(provs) >= 2:
        ind = _match_industry(q)
        filters = {"industry_l1": [ind]} if ind else {}
        return SemanticQuery(
            query_type=QueryType.comparison,
            metrics=[_rule_comparison_metric(q)],
            compare=[CompareTarget(dimension="province", values=provs[:2])],
            filters=filters,
            raw_query=query,
            source="rule",
        )

    # 双行业：取至少两个不同行业大类
    inds = _values_in_query_order(q, _INDUSTRY_KW)
    if len(inds) >= 2:
        return SemanticQuery(
            query_type=QueryType.comparison,
            metrics=[_rule_comparison_metric(q)],
            compare=[CompareTarget(dimension="industry_l1", values=inds[:2])],
            raw_query=query,
            source="rule",
        )

    return None


def prefer_trend_over_spurious_comparison(
    sq: SemanticQuery,
    query: str | None,
    *,
    intent: Any | None = None,
) -> SemanticQuery:
    """行业/趋势意图被 LLM 误判成地区对比时，拉回 trend（根契约：听 intent，非词表堆砌）。"""
    q = (query or "").strip()
    if not q:
        return sq
    region_ask = bool(re.search(r"地区|省份|各省|分省|按地区", q))
    if region_ask:
        return sq

    intent_fn = getattr(intent, "function", None) if intent is not None else None
    intent_dim = getattr(intent, "dimension", None) if intent is not None else None
    phrase_hit = bool(
        re.search(r"(各行业|行业).{0,8}(趋势|走向|走势|同比|对比)|趋势走向|同比趋势|行业趋势", q)
    )
    intent_hit = intent_fn == "trend" and intent_dim in (
        None,
        "",
        "industry",
        "industry_l1",
        "time",
    )
    if not (phrase_hit or intent_hit):
        return sq

    dims = list(sq.dimensions or [])
    looks_region = (
        sq.query_type == QueryType.comparison
        or "province" in dims
        or any(getattr(c, "dimension", None) == "province" for c in (sq.compare or []))
    )
    if not looks_region and sq.query_type == QueryType.trend:
        return sq

    if intent is not None:
        fixed = intent_to_semantic_query(intent)
        fixed.source = "corrected"
        return fixed
    out = sq.model_copy(deep=True)
    out.query_type = QueryType.trend
    out.dimensions = (
        ["industry_l1"] if "industry_l1" not in (out.dimensions or []) else out.dimensions
    )
    out.compare = []
    out.source = "corrected"
    return out


def merge_followup(sq: SemanticQuery, prev: SemanticQuery | None, query: str | None = None) -> SemanticQuery:
    """追问：从上一轮继承缺失槽位，覆盖当前句显式声明的槽位。"""
    if prev is None:
        return sq
    merged = sq.model_copy(deep=True)
    merged.followup = True

    # 纯槽位追问（无 metrics/dims/compare，query_type 落回默认 aggregation）→ 继承上一轮查询类型与指标
    if sq.query_type == QueryType.aggregation and not _has_explicit_slots(sq):
        merged.query_type = prev.query_type
        merged.metrics = list(prev.metrics or merged.metrics)
        merged.dimensions = list(prev.dimensions or merged.dimensions)

    if not merged.metrics:
        merged.metrics = list(prev.metrics or [])
    if not merged.dimensions:
        merged.dimensions = list(prev.dimensions or [])

    for k, v in (prev.filters or {}).items():
        if k not in merged.filters or not merged.filters[k]:
            merged.filters[k] = list(v)

    if not merged.entities:
        merged.entities = list(prev.entities or [])
    if merged.sort is None:
        merged.sort = prev.sort
    if merged.limit is None:
        merged.limit = prev.limit

    return merged


def semantic_query_to_dict(sq: SemanticQuery) -> dict[str, Any]:
    """JSON 安全（Enum → value），供 session_store / conclusion_store 持久化。"""
    return sq.model_dump(mode="json")


def semantic_query_from_dict(raw: dict | None) -> SemanticQuery | None:
    if not raw:
        return None
    try:
        return SemanticQuery.model_validate(raw)
    except Exception:
        return None
