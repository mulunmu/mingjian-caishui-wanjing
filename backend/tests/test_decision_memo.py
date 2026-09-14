"""决策备忘录层：BLUF 分轨 + Action Title + 定制场景映射。"""
from __future__ import annotations

from app.services.decision_memo import (
    GOVERNING_QUESTIONS,
    apply_memo_to_slice_context,
    build_bluf,
    build_enterprise_bluf,
    enrich_decision_pages,
    filter_empty_metrics,
    resolve_memo_scenario,
    risk_buckets,
)


def test_governing_questions_cover_four_plus_enterprise():
    for key in ("loan", "rating", "warn", "audit", "enterprise"):
        assert key in GOVERNING_QUESTIONS
        assert "？" in GOVERNING_QUESTIONS[key]


def test_resolve_custom_chapters_to_loan_audit_rating():
    assert resolve_memo_scenario("custom", [{"function": "score"}, {"function": "fraud"}, {"function": "authenticity"}, {"function": "benchmark"}]) == "loan"
    assert resolve_memo_scenario("custom", [{"function": "fraud"}, {"function": "authenticity"}, {"function": "tax"}, {"function": "signal"}]) == "audit"
    assert resolve_memo_scenario("custom", [{"function": "score"}, {"function": "trend"}, {"function": "benchmark"}]) == "rating"
    assert resolve_memo_scenario("custom", [{"function": "signal"}, {"function": "fraud"}, {"function": "tax"}]) == "warn"


def test_risk_buckets_three_way():
    b = risk_buckets({"低风险": 40, "中低风险": 50, "中等风险": 30, "中高风险": 20, "高风险": 10})
    assert b["approve"] == 40
    assert b["conditional"] == 80
    assert b["reject"] == 30
    assert b["total"] == 150


def test_bluf_tracks_differ_by_scenario():
    attr = {
        "sample_count": 100,
        "avg_score": 48.0,
        "risk_distribution": {"低风险": 20, "中等风险": 40, "高风险": 40},
        "industry_distribution": {"制造": 60, "服务": 40},
        "province_distribution": {"广东": 50},
        "drag_factors": [{"item": "进销错配", "count": 18}, {"item": "红字发票异常", "count": 12}],
    }
    chapters = [
        {
            "function": "fraud",
            "title": "发票异常",
            "claims": [{"claim": "进销错配命中 18 家。", "confidence": "computed"}],
            "meta": {"flagged_count": 18},
        }
    ]
    risks = ["进销错配（18 家）", "红字发票异常（12 家）"]
    loan = build_bluf(scenario_key="loan", chapters=chapters, attribution=attr, risks=risks)
    rating = build_bluf(scenario_key="rating", chapters=chapters, attribution=attr, risks=risks)
    warn = build_bluf(scenario_key="warn", chapters=chapters, attribution=attr, high_risk_ids={"a", "b"}, risks=risks)
    audit = build_bluf(scenario_key="audit", chapters=chapters, attribution=attr, high_risk_ids={"a", "b", "c"}, risks=risks)

    assert "可批" in loan["bluf"] and "附加条件" in loan["bluf"]
    assert "可授信占比" in rating["bluf"]
    assert "Top 异常信号" in warn["bluf"] or "异常信号" in warn["bluf"]
    assert "优先查" in audit["bluf"]
    # 四场景 BLUF 不得同质
    blufs = {loan["bluf"], rating["bluf"], warn["bluf"], audit["bluf"]}
    assert len(blufs) == 4
    for m in (loan, rating, warn, audit):
        assert "为什么：" not in m["bluf"]
        assert m["governing_question"]
        assert m["top_actions"]


def test_enrich_decision_pages_sets_action_title():
    chapters = [
        {
            "title": "六维经营表现画像",
            "function": "score",
            "claims": [{"claim": "样本经营表现偏弱，尾部集中在制造。", "confidence": "computed"}],
            "meta": {},
        }
    ]
    enrich_decision_pages(chapters, scenario_key="rating")
    assert chapters[0]["topic_title"] == "六维经营表现画像"
    assert chapters[0]["action_title"]
    assert chapters[0]["action_title"] != "六维经营表现画像"
    assert chapters[0]["verdict_paragraph"]
    assert "论断" not in chapters[0]["verdict_paragraph"]
    assert "…" not in chapters[0]["action_title"]
    assert len(chapters[0]["action_title"]) <= 40


def test_apply_memo_overwrites_homogenized_summary():
    ctx = {
        "summary_conclusion": "群体风险判断「中高风险」。为什么：营收偏差（85%）",
        "executive_summary": "旧摘要",
        "cover_meta": {},
        "chapters": [],
    }
    attr = {
        "sample_count": 50,
        "avg_score": 40.0,
        "risk_distribution": {"高风险": 20, "中等风险": 30},
        "drag_factors": [{"item": "进销错配", "count": 10}],
        "industry_distribution": {"制造": 50},
    }
    apply_memo_to_slice_context(
        ctx,
        scenario_key="loan",
        chapters=[],
        attribution=attr,
        risks=["进销错配（10 家）"],
    )
    assert "为什么：" not in (ctx["summary_conclusion"] or "")
    assert "可批" in ctx["summary_conclusion"]
    assert ctx["executive_summary"] == ctx["summary_conclusion"]
    assert ctx["governing_question"] == GOVERNING_QUESTIONS["loan"]
    assert ctx.get("summary_evidence")
    assert any("进货" in x or "销货" in x or "错配" in x for x in ctx["summary_evidence"])

def test_enterprise_bluf_and_empty_metric_filter():
    memo = build_enterprise_bluf(
        risk_level="中高风险",
        hit_risk_count=3,
        checked_metric_count=8,
        weak_titles=["发票", "税务健康"],
        risk_points=["进销错配"],
        advice=["先核红冲对应销售方名单。"],
    )
    assert "先盯" in memo["bluf"]
    assert memo["governing_question"] == GOVERNING_QUESTIONS["enterprise"]
    kept = filter_empty_metrics(
        [
            {"label": "毛利率", "value": "20%", "rating": "达标"},
            {"label": "空", "value": "【暂无可用数据】", "rating": "【暂无可用数据】"},
            {"label": "无", "value": None, "rating": ""},
        ]
    )
    assert len(kept) == 1
    assert kept[0]["label"] == "毛利率"
