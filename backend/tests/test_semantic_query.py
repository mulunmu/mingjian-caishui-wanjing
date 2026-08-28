"""SemanticQuery 校正器 / 转换器 / 追问合并 — 纯单测（无 DB、无 LLM）。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.semantic_query import SemanticQuery
from app.services.intent_engine import IntentResult
from app.services import semantic_query


def test_corrector_drops_unknown_metric_and_aliases():
    sq = SemanticQuery(
        query_type="aggregation",
        metrics=["不存在的指标", "信用分"],
        filters={"industry_l1": ["IT"], "province": ["深圳"]},
    )
    out = semantic_query.correct_semantic_query(sq)
    # 未知指标被丢弃；别名「信用分」→ credit_score
    assert out.metrics == ["credit_score"]
    # 行业「IT」→「IT软件」；省份「深圳」→「广东」
    assert out.filters["industry_l1"] == ["IT软件"]
    assert out.filters["province"] == ["广东"]
    assert out.source == "corrected"


def test_corrector_sets_default_metric():
    out = semantic_query.correct_semantic_query(SemanticQuery(query_type="ranking", metrics=[]))
    assert out.metrics == ["overall_score"]
    # 相关性需两个 metric
    corr = semantic_query.correct_semantic_query(SemanticQuery(query_type="correlation", metrics=[]))
    assert corr.metrics == ["credit_score", "revenue_yoy"]


def test_intent_to_semantic_query_covers_rule_functions():
    cases = [
        # (function, dimension) -> (query_type, metrics)
        (("trend", "industry"), ("trend", ["revenue_yoy"])),
        (("trend", "region"), ("trend", ["revenue_yoy"])),
        (("score", "overall"), ("aggregation", ["overall_score"])),
        (("score", "industry"), ("aggregation", ["credit_score"])),
        (("benchmark", "industry"), ("aggregation", ["credit_score"])),
        (("authenticity", "industry"), ("aggregation", ["authenticity_score"])),
        (("fraud", "industry"), ("aggregation", ["fraud_composite_score"])),
        (("signal", "signal"), ("distribution", ["signal_total"])),
        (("report", "overall"), ("aggregation", ["credit_score"])),
        (("email_report", "overall"), ("aggregation", ["credit_score"])),
        (("general", "overall"), ("aggregation", ["credit_score"])),
    ]
    for (fn, dim), (qt, metrics) in cases:
        intent = IntentResult(function=fn, dimension=dim, intent=f"{fn}_{dim}")
        sq = semantic_query.intent_to_semantic_query(intent)
        assert sq.query_type == qt, f"{fn}/{dim}: got {sq.query_type}"
        assert sq.metrics == metrics, f"{fn}/{dim}: got {sq.metrics}"
        assert sq.source == "rule"


def test_intent_to_semantic_query_preserves_filters():
    intent = IntentResult(
        function="score", dimension="region", industry_l1="制造", province="广东"
    )
    sq = semantic_query.intent_to_semantic_query(intent)
    assert sq.filters["industry_l1"] == ["制造"]
    assert sq.filters["province"] == ["广东"]


def test_merge_followup_fills_and_overrides_province():
    prev = SemanticQuery(
        query_type="ranking",
        metrics=["credit_score"],
        dimensions=["industry_l1"],
        filters={"industry_l1": ["制造"]},
        limit=5,
    )
    # 纯槽位追问（无 metrics/dims/compare，仅显式声明省份）
    cur = SemanticQuery(query_type="aggregation", filters={"province": ["江苏"]})
    merged = semantic_query.merge_followup(cur, prev, "那江苏呢")
    # 继承上一轮 query_type / metrics / dimensions / limit
    assert merged.query_type == "ranking"
    assert merged.metrics == ["credit_score"]
    assert merged.dimensions == ["industry_l1"]
    assert merged.limit == 5
    # 显式省份覆盖，行业过滤继承
    assert merged.filters["province"] == ["江苏"]
    assert merged.filters["industry_l1"] == ["制造"]
    assert merged.followup is True


def test_merge_followup_without_prev_returns_same():
    sq = SemanticQuery(query_type="aggregation", metrics=["credit_score"])
    assert semantic_query.merge_followup(sq, None, "追问") is sq


def test_semantic_query_roundtrip_dict():
    sq = SemanticQuery(
        query_type="comparison",
        metrics=["credit_score"],
        compare=[{"dimension": "province", "values": ["广东", "江苏"]}],
    )
    raw = semantic_query.semantic_query_to_dict(sq)
    assert raw["query_type"] == "comparison"
    restored = semantic_query.semantic_query_from_dict(raw)
    assert restored is not None
    assert restored.query_type == "comparison"
    assert restored.compare[0].values == ["广东", "江苏"]
    # 非法输入安全返回 None
    assert semantic_query.semantic_query_from_dict(None) is None
    assert semantic_query.semantic_query_from_dict("not-a-dict") is None


def test_query_type_to_function_never_general_for_analysis():
    from app.schemas.semantic_query import QueryType

    for qt in [
        QueryType.trend,
        QueryType.distribution,
        QueryType.comparison,
        QueryType.lookup,
        QueryType.aggregation,
        QueryType.ranking,
        QueryType.correlation,
        QueryType.segmentation,
    ]:
        sq = SemanticQuery(query_type=qt, metrics=["credit_score"])
        fn = semantic_query.query_type_to_function(sq)
        assert fn != "general", f"{qt} 不应退回 general"
    # faq / methodology 显式返回 general（不污染分析覆盖度）
    assert semantic_query.query_type_to_function(SemanticQuery(query_type="faq")) == "general"
    assert semantic_query.query_type_to_function(SemanticQuery(query_type="methodology")) == "general"


def test_detect_rule_comparison_two_provinces_with_industry_filter():
    from app.schemas.semantic_query import QueryType

    sq = semantic_query.detect_rule_comparison("江西和湖南制造业信用分对比")
    assert sq is not None
    assert sq.query_type == QueryType.comparison
    assert sq.compare[0].dimension == "province"
    assert sq.compare[0].values == ["江西", "湖南"]
    assert sq.filters == {"industry_l1": ["制造"]}
    assert sq.metrics == ["credit_score"]


def test_detect_rule_comparison_two_provinces_no_filter():
    from app.schemas.semantic_query import QueryType

    sq = semantic_query.detect_rule_comparison("广东和江苏的信用分对比")
    assert sq is not None and sq.query_type == QueryType.comparison
    assert sq.compare[0].values == ["广东", "江苏"]
    assert sq.filters == {}


def test_detect_rule_comparison_two_industries_uses_revenue_metric():
    from app.schemas.semantic_query import QueryType

    sq = semantic_query.detect_rule_comparison("制造业和批发零售的营收对比")
    assert sq is not None and sq.query_type == QueryType.comparison
    assert sq.compare[0].dimension == "industry_l1"
    assert sq.compare[0].values == ["制造", "批发零售"]
    assert sq.metrics == ["revenue_yoy"]


def test_detect_rule_comparison_ignores_single_sided_queries():
    # 单边问法（仅一个省 / 仅“各行业”）不应被误判成双值对比
    assert semantic_query.detect_rule_comparison("各地区信用分对比") is None
    assert semantic_query.detect_rule_comparison("广东地区信用分对比") is None
    assert semantic_query.detect_rule_comparison("跟同行对标") is None
    assert semantic_query.detect_rule_comparison("分析各行业的趋势走向") is None


def test_detect_faq_or_methodology_routes_questions_not_commands():
    from app.schemas.semantic_query import QueryType

    # 产品说明问句 → faq（含被「报告*」关键词劫持的「报告怎么生成」）
    faq = semantic_query.detect_faq_or_methodology("报告怎么生成")
    assert faq is not None and faq.query_type == QueryType.faq
    usage = semantic_query.detect_faq_or_methodology("这个系统能做什么")
    assert usage is not None and usage.query_type == QueryType.faq
    # 口径问句 → methodology
    meth = semantic_query.detect_faq_or_methodology("综合评分怎么算的")
    assert meth is not None and meth.query_type == QueryType.methodology
    # 祈使指令（生成/导出报告）→ 不拦截，交给报告意图
    assert semantic_query.detect_faq_or_methodology("生成报告") is None
    assert semantic_query.detect_faq_or_methodology("生成行业趋势风控报告") is None
    assert semantic_query.detect_faq_or_methodology("导出报告") is None
    # 无关分析问法 → None
    assert semantic_query.detect_faq_or_methodology("分析各行业的趋势走向") is None
    # C1：研判问句不得因「数据/报告」被 FAQ 劫持
    assert semantic_query.detect_faq_or_methodology("各地区数据怎么样") is None
    assert semantic_query.detect_faq_or_methodology("营收数据可以对比吗") is None
    assert semantic_query.detect_faq_or_methodology("报告覆盖了哪些维度") is None
