"""切片报告 + 抗幻觉校验"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services import conclusion_store, hallucination_guard
from app.services.report_templates import resolve_scenario, get_scenario
from app.services.slice_report import (
    _chapter_claims,
    _fallback_executive_summary,
    _flagged_count,
    _resolve_scenario_kpis,
    _score_to_risk_level,
    _scenario_summary_block,
    _slice_ratio_mean,
    build_report_detail,
)


def test_resolve_scenario_general():
    # 默认（未命中关键词）→ 综合尽调
    assert resolve_scenario(query="生成报告") == "due_diligence"
    assert resolve_scenario(query="欺诈报告") == "fraud"
    assert resolve_scenario(query="财务健康体检") == "financial"
    assert resolve_scenario(query="税务合规") == "tax"
    assert resolve_scenario(query="企业画像") == "profile"
    # 旧场景 key 归一化（历史文件名 / 旧 API 兼容）
    assert resolve_scenario(scenario="general") == "due_diligence"
    assert resolve_scenario(scenario="fundamental") == "financial"


def test_resolve_scenario_rejects_unknown_explicit():
    with pytest.raises(ValueError, match="未知报告场景"):
        resolve_scenario(scenario="typo_scenario")


def test_resolve_scenario_overview():
    """总览/汇总 → overview，且「综合总览」须先于「综合」命中（避免归到 due_diligence）。"""
    assert resolve_scenario(query="生成总览报告") == "overview"
    assert resolve_scenario(query="生成综合总览报告") == "overview"
    assert resolve_scenario(query="生成汇总报告") == "overview"
    assert resolve_scenario(scenario="overview") == "overview"
    spec = get_scenario("overview")
    assert spec["title"] == "综合总览报告"


def test_financial_threshold_table_disclosed():
    """四能力判定阈值可回溯、非黑盒：披露表覆盖所有带评级方向的比率。"""
    from app.services.financial_benchmarks import FINANCIAL_THRESHOLD_TABLE, FINANCIAL_RATIOS

    rows = FINANCIAL_THRESHOLD_TABLE()
    # 有明确 warn_dir 的比率都应披露
    expect = sum(1 for c in FINANCIAL_RATIOS.values() if c.get("warn_dir") is not None)
    assert len(rows) == expect
    assert len(rows) >= 8
    labels = {r["label"] for r in rows}
    assert "资产负债率" in labels
    assert all(r["group"] and r["rule"] and r["threshold"] for r in rows)


def test_scenario_has_chapters():
    spec = get_scenario("due_diligence")
    assert spec["title"]
    assert len(spec["chapters"]) >= 3


def test_portfolio_scenarios_portrait_and_alert():
    from app.services.report_templates import PORTFOLIO_SCENARIO_KEYS, SCENARIOS, resolve_scenario

    assert set(PORTFOLIO_SCENARIO_KEYS) == {"portrait", "alert"}
    assert "portrait" in SCENARIOS and "alert" in SCENARIOS
    for key in PORTFOLIO_SCENARIO_KEYS:
        spec = SCENARIOS[key]
        assert spec["title"] and spec["subtitle"], key
        assert spec["cover"]["motif"] in {"ledger", "seal", "magnifier", "compass", "badge"}, key
        assert len(spec["chapters"]) >= 3, key
    # 旧 key 归一到两主题
    assert resolve_scenario(scenario="profile") == "portrait"
    assert resolve_scenario(scenario="due_diligence") == "alert"
    assert resolve_scenario(scenario="financial") == "alert"
    # 预警覆盖四类数据
    assert set(SCENARIOS["alert"]["data_focus"]) == {
        "财务数据", "税务数据", "发票数据", "企业基础信息",
    }


def test_has_scenario_keyword_and_path_prompts():
    from app.services.report_templates import has_scenario_keyword, scenario_path_prompts

    # 通用「生成报告」未命中场景关键词 → 罗列路径
    assert has_scenario_keyword("生成报告") is False
    assert has_scenario_keyword("帮我出一份报告") is False
    # 指定场景 → 直接生成
    assert has_scenario_keyword("生成风险预警报告") is True
    assert has_scenario_keyword("样本库画像") is True
    assert has_scenario_keyword("发票舞弊报告") is True
    # 定制化不再吞意图
    assert has_scenario_keyword("生成定制报告") is False
    assert has_scenario_keyword("生成定制化的报告") is False

    prompts = scenario_path_prompts()
    assert any("画像" in p for p in prompts)
    assert any("预警" in p for p in prompts)
    assert any("指定企业" in p for p in prompts)
    assert len(prompts) == 3


def test_scope_label():
    from app.services.report_templates import scope_label

    assert scope_label("制造", None) == "制造"
    assert scope_label(None, "广东") == "广东"
    assert scope_label(None, None) == ""
    # 行业优先于地区（范围化标题的前缀）
    assert scope_label("制造", "广东") == "制造"


def test_scenario_tone_profiles():
    from app.services.report_templates import (
        TONE_PROFILES,
        BANNED_AI_PHRASES,
        get_scenario_tone,
    )

    # 五场景 + 个体报告均有人格与文风
    for key in ("financial", "tax", "fraud", "due_diligence", "profile", "enterprise"):
        assert TONE_PROFILES[key]["persona"], key
        assert TONE_PROFILES[key]["style"], key
    # 回退：旧 key → 综合尽调语气
    assert get_scenario_tone("general")["persona"] == TONE_PROFILES["due_diligence"]["persona"]
    assert get_scenario_tone("financial")["persona"] == "资深财务分析师"
    assert get_scenario_tone("tax")["persona"] == "税务合规顾问"
    # 去 AI 味禁用词覆盖常见套话
    for kw in ("综上所述", "首先", "值得注意的是", "总而言之"):
        assert kw in BANNED_AI_PHRASES


def test_tone_prompt_injects_persona_and_banned():
    from app.services import llm_reply

    p = llm_reply._tone_prompt({"persona": "资深财务分析师", "style": "简洁克制。"})
    assert "资深财务分析师" in p
    assert "禁用套话" in p
    assert llm_reply._tone_prompt(None) == ""


def test_filter_unanchored_sentences():
    claims = [
        Claim(
            claim="样本 10 家。",
            value=ClaimValue(metric="n", number=10, unit="家"),
            trace=ClaimTrace(table="core_metrics", field="enterprise_id", query_id="Q"),
            confidence="computed",
        )
    ]
    kept, dropped = hallucination_guard.filter_unanchored_sentences(
        ["样本 10 家。", "逾期率 99.9%。"], claims
    )
    assert kept == ["样本 10 家。"]
    assert len(dropped) == 1


def test_validate_report_chapters_ok():
    chapters = [
        {
            "title": "趋势",
            "claims": [
                {
                    "claim": "制造行业同比 5%。",
                    "confidence": "computed",
                    "trace": {"table": "core_metrics", "field": "revenue_yoy", "query_id": "Q1"},
                }
            ],
        }
    ]
    v = hallucination_guard.validate_report_chapters(chapters)
    assert v["ok"] is True
    assert v["unanchored"] == 0


def test_validate_report_chapters_rejects_asserted():
    chapters = [
        {
            "title": "x",
            "claims": [{"claim": "无锚点", "confidence": "asserted"}],
        }
    ]
    v = hallucination_guard.validate_report_chapters(chapters)
    assert v["ok"] is False
    assert v["unanchored"] >= 1


def test_validate_report_chapters_detects_risk_direction_on_clean_chapter():
    """达标章（无风险结论）解读段出现「承压/需核查」→ 渲染前校验拦截（claim 唯一化铁律）。"""
    chapters = [
        {
            "title": "偿债能力",
            "claims": [
                {
                    "claim": "流动比率均值 1.80（达标）。",
                    "confidence": "computed",
                    "value": {"metric": "current_ratio", "number": 1.8, "unit": ""},
                    "trace": {"table": "enterprise_financials", "field": "current_ratio", "query_id": "Q1"},
                }
            ],
            "narration": "流动比率 1.80，偿债能力承压，需核查再融资安排。",
        }
    ]
    v = hallucination_guard.validate_report_chapters(chapters)
    assert v["risk_contradictions"] >= 1
    assert v["ok"] is False


def test_validate_report_chapters_detects_unanchored_number():
    """解读段出现 claim 中不存在的数字 → 数字锚点校验拦截。"""
    chapters = [
        {
            "title": "趋势",
            "claims": [
                {
                    "claim": "制造行业同比 5%。",
                    "confidence": "computed",
                    "value": {"metric": "avg_revenue_yoy", "number": 5.0, "unit": "%"},
                    "trace": {"table": "core_metrics", "field": "revenue_yoy", "query_id": "Q1"},
                }
            ],
            "narration": "逾期率高达 99.9%。",
        }
    ]
    v = hallucination_guard.validate_report_chapters(chapters)
    assert v["number_unanchored"] >= 1
    assert v["ok"] is False


def test_validate_report_chapters_allows_clean_narration():
    """达标章 + 有锚点且无风险方向词 → 校验通过。"""
    chapters = [
        {
            "title": "偿债能力",
            "claims": [
                {
                    "claim": "流动比率均值 1.80（达标）。",
                    "confidence": "computed",
                    "value": {"metric": "current_ratio", "number": 1.8, "unit": ""},
                    "trace": {"table": "enterprise_financials", "field": "current_ratio", "query_id": "Q1"},
                }
            ],
            "narration": "流动比率 1.80，偿债能力稳健。",
        }
    ]
    v = hallucination_guard.validate_report_chapters(chapters)
    assert v["ok"] is True
    assert v["risk_contradictions"] == 0
    assert v["number_unanchored"] == 0


def test_enforce_chapter_integrity_strips_bad_narration_and_asserted():
    """硬门禁：剥离 asserted claim + 无锚点/风险矛盾解读句，复检应通过。"""
    chapters = [
        {
            "title": "偿债能力",
            "claims": [
                {
                    "claim": "流动比率均值 1.80（达标）。",
                    "confidence": "computed",
                    "value": {"metric": "current_ratio", "number": 1.8, "unit": ""},
                    "trace": {"table": "enterprise_financials", "field": "current_ratio", "query_id": "Q1"},
                },
                {"claim": "编造结论", "confidence": "asserted"},
            ],
            "narration": "流动比率 1.80，偿债能力承压。逾期率 99.9%。流动比率 1.80 表现稳健。",
        }
    ]
    enf = hallucination_guard.enforce_chapter_integrity(chapters)
    assert enf["dropped_claims"] == 1
    assert enf["stripped_sentences"] >= 2
    assert "编造" not in str(chapters[0]["claims"])
    assert "承压" not in (chapters[0].get("narration") or "")
    assert "99.9" not in (chapters[0].get("narration") or "")
    v = hallucination_guard.validate_report_chapters(chapters)
    assert v["ok"] is True


def test_compose_story_and_purpose_from_claims():
    from app.services.report_templates import (
        compose_purpose_from_claims,
        compose_story_from_chapters,
    )

    assert "弃权" in compose_purpose_from_claims("结构目的", [])
    assert compose_purpose_from_claims("结构目的。", [{"claim": "有结论"}]) == "结构目的。"
    story = compose_story_from_chapters(
        [
            {"claims": [{"claim": "制造业同比 5%"}]},
            {"claims": [{"claim": "纳税准时率 98%。"}]},
        ]
    )
    assert "制造业同比 5%。" in story
    assert "纳税准时率 98%。" in story
    assert "弃权" in compose_story_from_chapters([{"claims": []}])


def test_enforce_cross_surface_blanks_unaligned_kpi_and_strips_story():
    chapters = [
        {
            "title": "趋势",
            "claims": [
                {
                    "claim": "制造行业同比 5%。",
                    "confidence": "computed",
                    "value": {"metric": "avg_revenue_yoy", "number": 5.0, "unit": "%"},
                    "trace": {"table": "core_metrics", "field": "revenue_yoy", "query_id": "Q1"},
                }
            ],
        }
    ]
    kpis = [
        {"label": "样本规模", "value": "5", "unit": "家"},  # 对齐 claim 数字 5
        {"label": "幽灵指标", "value": "99.9", "unit": "%"},  # 无 claim 锚点 → 弃权
        {"label": "溯源卡", "value": "12", "unit": "家", "metric": "sample_count", "source": "assessment"},
    ]
    story = "制造行业同比 5%。另有逾期率 99.9% 需关注。"
    exec_sum = "样本同比 5%，表现平稳。"
    aligned, new_story, new_exec, stats = hallucination_guard.enforce_cross_surface(
        chapters=chapters,
        summary_kpis=kpis,
        story=story,
        executive_summary=exec_sum,
    )
    assert stats["blanked_kpis"] == 1
    assert aligned[1]["value"] == "—"
    assert aligned[2]["value"] == "12"  # traced KPI 保留
    assert "99.9" not in new_story
    assert "5" in new_story or "5%" in new_story
    cross = hallucination_guard.validate_cross_surface(
        chapters=chapters,
        summary_kpis=aligned,
        story=new_story,
        executive_summary=new_exec,
    )
    assert cross["ok"] is True


def test_assert_report_renderable_rejects_empty():
    from app.services.slice_report import _assert_report_renderable
    import pytest

    with pytest.raises(ValueError, match="无可溯源"):
        _assert_report_renderable({"validation": {"empty": True, "total_claims": 0}})
    _assert_report_renderable({"validation": {"empty": False, "total_claims": 3}})


@pytest.mark.asyncio
async def test_chapter_claims_matches_dimension():
    """报告章节按 function+dimension 复用会话结论，不串维度。"""
    sid = "test_sid_dim_match"
    conclusion_store.save_conclusion(
        session_id=sid,
        function="trend",
        dimension="industry",
        claims=[
            Claim(
                claim="行业趋势结论",
                value=ClaimValue(metric="n", number=1, unit=""),
                trace=ClaimTrace(table="core_metrics", field="revenue_yoy", query_id="Q1"),
                confidence="computed",
            )
        ],
        followups=[],
    )
    conclusion_store.save_conclusion(
        session_id=sid,
        function="trend",
        dimension="region",
        claims=[
            Claim(
                claim="地区趋势结论",
                value=ClaimValue(metric="n", number=2, unit=""),
                trace=ClaimTrace(table="core_metrics", field="revenue_yoy", query_id="Q2"),
                confidence="computed",
            )
        ],
        followups=[],
    )

    claims, _meta = await _chapter_claims(None, sid, "trend", "industry")
    texts = [c.claim for c in claims]
    assert "行业趋势结论" in texts
    assert "地区趋势结论" not in texts


def test_fallback_executive_summary():
    kpis = [
        {"label": "样本规模", "value": "10", "unit": "家"},
        {"label": "关注行业", "value": "制造", "unit": ""},
    ]
    chapters = [{"title": "行业趋势"}, {"title": "风险信号"}]
    s = _fallback_executive_summary(kpis, chapters)
    assert "10" in s and "制造" in s
    # 结论前置、风控专家口吻：不再罗列章节标题的「本报告覆盖…」方法论句式
    assert "本报告" not in s
    assert "优先核查" in s


def test_fallback_executive_summary_skips_empty_kpi():
    """KPI 值为「—」（弃权）→ 不进入摘要文本（空数据消除）。"""
    kpis = [
        {"label": "样本规模", "value": "10", "unit": "家"},
        {"label": "关注行业", "value": "—", "unit": ""},
    ]
    s = _fallback_executive_summary(kpis, [{"title": "行业趋势"}])
    assert "10" in s
    assert "关注行业" not in s  # 「—」卡被过滤，label 也不出现


def test_score_to_risk_level_aligns_with_scoring_layer():
    assert _score_to_risk_level(85) == "低风险"
    assert _score_to_risk_level(70) == "中低风险"
    assert _score_to_risk_level(55) == "中等风险"
    assert _score_to_risk_level(40) == "中高风险"
    assert _score_to_risk_level(20) == "高风险"


def test_scenario_summary_block_scenario_specific():
    """场景化：专项报告优势/风险来自本场景章节，不复读全样本六维归因（杜绝跑题）。"""
    attr = {
        "avg_score": 55.0,
        "sample_count": 12,
        "dimensions": {},
        "drag_factors": [{"item": "税务违法", "count": 99}],
    }
    financial_ch = {
        "function": "financial",
        "claims": [
            {
                "claim": "毛利率均值 30.5%（达标，样本 12）。",
                "value": {"metric": "gross_margin", "number": 30.5, "unit": "%"},
            },
            {
                "claim": "资产负债率均值 82.0%（预警，样本 12）。",
                "value": {"metric": "debt_ratio", "number": 82.0, "unit": "%"},
            },
        ],
        "meta": {"sample_count": 12},
    }
    block = _scenario_summary_block([financial_ch], attr, set())
    # 结论仍 L1 统一（业务语言：不暴露原始均分）
    assert block["conclusion"] == "群体风险判断「中等风险」，样本 12 家"
    # 优势/风险来自财务章节；六维 drag_factors 的「税务违法 99 家」绝不出现在财务报告摘要
    assert block["strengths"] == ["「毛利率」30.5%（达标）"]
    assert block["risks"] == ["「资产负债率」82.0%（预警）"]


def test_scenario_summary_block_scenario_subject_clause():
    """L2 语气层：专项场景结论补「维度主语」，引用 L1 维度分；综合场景/无数据弃权。"""
    attr = {
        "avg_score": 43.1,
        "sample_count": 193,
        "dimensions": {"finance": {"label": "财务健康", "score": 52.0}},
        "drag_factors": [],
    }
    block = _scenario_summary_block([], attr, set(), scenario="financial")
    assert block["conclusion"] == (
        "群体风险判断「中高风险」，样本 193 家；财务健康维度表现中等"
    )
    # 无单一维度锚点的综合场景：不补主语（结论仍 L1 统一）
    block2 = _scenario_summary_block([], attr, set(), scenario="due_diligence")
    assert block2["conclusion"] == "群体风险判断「中高风险」，样本 193 家"
    # 维度无数据（0=弃权 sentinel）：不补主语，杜绝「0.0 分=高风险」式虚假结论
    attr_empty = {
        "avg_score": 43.1,
        "sample_count": 193,
        "dimensions": {"finance": {"label": "财务健康", "score": 0.0}},
    }
    block3 = _scenario_summary_block([], attr_empty, set(), scenario="financial")
    assert block3["conclusion"] == "群体风险判断「中高风险」，样本 193 家"


def test_scenario_summary_block_six_dim_via_score():
    """六维归因只经 score 章（meta.attribution）携带，总览/尽调场景专用。"""
    attr = {"avg_score": 47.0, "sample_count": 193}
    score_ch = {
        "function": "score",
        "claims": [],
        "meta": {
            "sample_count": 193,
            "attribution": {
                "dimensions": {"legal": {"label": "法律合规", "score": 70.0}},
                "drag_factors": [{"item": "税务违法", "count": 12}],
                "sample_count": 193,
            },
        },
    }
    block = _scenario_summary_block([score_ch], attr, {"e1", "e2", "e3"})
    assert block["strengths"] == ["「法律合规」维度表现稳健"]
    assert block["risks"] == [
        "税务违法 12 家 / 样本 193 家（6.2%）",
        "重点关注主体 3 家 / 样本 193 家（1.6%）",
    ]


def test_scenario_summary_block_abstains_empty():
    """无章节/无评分 → 全弃权（结论空、优势风险空），不硬造。"""
    block = _scenario_summary_block([], {"avg_score": None, "dimensions": {}, "drag_factors": []}, set())
    assert block["conclusion"] == ""
    assert block["strengths"] == []
    assert block["risks"] == []


def test_scenario_summary_block_no_false_strength_on_dirty_sample():
    """清净主体占比过低不构成优势（弃权），杜绝把 5.7% 清净当「主要优势」。"""
    signal_ch = {
        "function": "signal",
        "claims": [],
        "meta": {
            "sample_count": 193,
            "unique_affected": ["e1"] * 182,
            "tax_violation": 83,
            "high_dev": 50,
            "low_credit": 30,
            "multi_hit_ge2": 10,
        },
    }
    block = _scenario_summary_block([signal_ch], {"avg_score": 43.1, "sample_count": 193}, set())
    assert block["strengths"] == []
    assert "税务违法 83 家 / 样本 193 家（43.0%）" in block["risks"]


def test_scenario_summary_block_clean_strength_when_majority():
    """清净主体占比 ≥80% 才构成优势锚点。"""
    signal_ch = {
        "function": "signal",
        "claims": [],
        "meta": {"sample_count": 100, "unique_affected": ["e1"] * 5, "tax_violation": 5},
    }
    block = _scenario_summary_block([signal_ch], {"avg_score": 80.0, "sample_count": 100}, set())
    assert block["strengths"] == ["无风险信号主体 95 家（占比 95.0%）"]


def test_slice_ratio_mean_abstain_zero():
    from decimal import Decimal

    from app.models.core_metrics import CoreMetrics

    rows = [
        CoreMetrics(enterprise_id="e1", gross_margin=Decimal("0.2")),
        CoreMetrics(enterprise_id="e2", gross_margin=Decimal("0.4")),
        CoreMetrics(enterprise_id="e3", gross_margin=Decimal("0")),  # 0=弃权，不混入
    ]
    assert _slice_ratio_mean(rows, "gross_margin") == pytest.approx(0.3)
    # 全 0 → None（弃权）
    assert _slice_ratio_mean([CoreMetrics(enterprise_id="e4")], "gross_margin") is None


def test_flagged_count_signals():
    from app.models.core_metrics import CoreMetrics

    rows = [
        CoreMetrics(enterprise_id="e1", tax_violation_cnt=1),
        CoreMetrics(enterprise_id="e2", is_dishonesty=True),
        CoreMetrics(enterprise_id="e3", credit_level="D"),
        CoreMetrics(enterprise_id="e4"),  # 无信号
    ]
    assert _flagged_count(rows) == 3


@pytest.mark.asyncio
async def test_resolve_scenario_kpis_tax(monkeypatch):
    """税务场景封面 KPI：从 core_metrics 聚合，0=弃权，metric+source 可回溯。"""
    from decimal import Decimal

    from app.models.core_metrics import CoreMetrics
    from app.services import assessment

    rows = [
        CoreMetrics(
            enterprise_id="e1", province="广东", industry_l1="制造", credit_level="A",
            tax_on_time_rate=Decimal("0.9"), vat_burden=Decimal("0.05"),
            income_tax_burden=Decimal("0.03"), tax_late_penalty_cnt=2,
        ),
        CoreMetrics(
            enterprise_id="e2", province="广东", industry_l1="制造", credit_level="B",
            tax_on_time_rate=Decimal("0.8"), vat_burden=Decimal("0.04"),
            income_tax_burden=Decimal("0.02"), tax_late_penalty_cnt=1,
        ),
    ]

    async def _fake_cache(db):
        return rows

    monkeypatch.setattr(assessment, "_ensure_cache", _fake_cache)

    spec_kpis = [
        {"label": "纳税准时率", "metric": "tax_on_time_rate", "unit": "%", "source": "core_metrics"},
        {"label": "增值税税负", "metric": "vat_burden", "unit": "%", "source": "core_metrics"},
        {"label": "所得税税负", "metric": "income_tax_burden", "unit": "%", "source": "core_metrics"},
        {"label": "滞纳/处罚次数", "metric": "tax_late_penalty_cnt", "unit": "次", "source": "core_metrics"},
    ]
    resolved = await _resolve_scenario_kpis(None, spec_kpis, {"avg_score": 70.0})
    by_metric = {k["metric"]: k for k in resolved}

    assert by_metric["tax_on_time_rate"]["value"] == "85.0"   # (0.9+0.8)/2 ×100
    assert by_metric["vat_burden"]["value"] == "4.5"          # (0.05+0.04)/2 ×100
    assert by_metric["income_tax_burden"]["value"] == "2.5"   # (0.03+0.02)/2 ×100
    assert by_metric["tax_late_penalty_cnt"]["value"] == "3"  # 2+1
    # metric+source 可回溯
    assert by_metric["tax_on_time_rate"]["trace"] == "core_metrics.tax_on_time_rate"
    assert by_metric["vat_burden"]["source"] == "core_metrics"


@pytest.mark.asyncio
async def test_resolve_scenario_kpis_industry_scoped(monkeypatch):
    """范围化：industry_l1 过滤后封面 KPI 只聚合该行业样本（报告定制端到端）。"""
    from decimal import Decimal

    from app.models.core_metrics import CoreMetrics
    from app.services import assessment

    rows = [
        CoreMetrics(
            enterprise_id="e1", province="广东", industry_l1="制造", credit_level="A",
            tax_on_time_rate=Decimal("0.9"), vat_burden=Decimal("0.05"),
        ),
        CoreMetrics(
            enterprise_id="e2", province="广东", industry_l1="制造", credit_level="B",
            tax_on_time_rate=Decimal("0.7"), vat_burden=Decimal("0.03"),
        ),
        # 非目标行业：应被过滤，不参与聚合
        CoreMetrics(
            enterprise_id="e3", province="广东", industry_l1="批发", credit_level="A",
            tax_on_time_rate=Decimal("0.1"), vat_burden=Decimal("0.01"),
        ),
    ]

    async def _fake_cache(db):
        return rows

    monkeypatch.setattr(assessment, "_ensure_cache", _fake_cache)

    spec_kpis = [
        {"label": "纳税准时率", "metric": "tax_on_time_rate", "unit": "%", "source": "core_metrics"},
        {"label": "增值税税负", "metric": "vat_burden", "unit": "%", "source": "core_metrics"},
    ]
    resolved = await _resolve_scenario_kpis(None, spec_kpis, {"avg_score": 70.0}, industry_l1="制造")
    by_metric = {k["metric"]: k for k in resolved}

    assert by_metric["tax_on_time_rate"]["value"] == "80.0"   # (0.9+0.7)/2 ×100，批发 0.1 被过滤
    assert by_metric["vat_burden"]["value"] == "4.0"          # (0.05+0.03)/2 ×100


@pytest.mark.asyncio
async def test_resolve_scenario_kpis_abstain_unavailable(monkeypatch):
    """无干净来源（fraud 引擎/同业分位）→ 弃权「—」，不编造。"""
    from decimal import Decimal

    from app.models.core_metrics import CoreMetrics
    from app.services import assessment

    async def _fake_cache(db):
        return [CoreMetrics(enterprise_id="e1", industry_l1="制造", credit_level="A")]

    monkeypatch.setattr(assessment, "_ensure_cache", _fake_cache)

    spec_kpis = [
        {"label": "舞弊信号数", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
        {"label": "同业分位", "metric": "benchmark_percentile", "unit": "%", "source": "industry_benchmark"},
    ]
    resolved = await _resolve_scenario_kpis(None, spec_kpis, {"avg_score": None})
    assert [k["value"] for k in resolved] == ["—", "—"]


@pytest.mark.asyncio
async def test_resolve_scenario_kpis_fraud(monkeypatch):
    """fraud 场景封面 KPI：由反欺诈引擎批算聚合，占比=命中主体/样本。"""
    from app.models.core_metrics import CoreMetrics
    from app.services import assessment, fraud_engine

    rows = [
        CoreMetrics(enterprise_id="e1", display_label="e1", industry_l1="制造"),
        CoreMetrics(enterprise_id="e2", display_label="e2", industry_l1="制造"),
    ]

    async def _fake_cache(db):
        return rows

    monkeypatch.setattr(assessment, "_ensure_cache", _fake_cache)

    def _fake_batch(rows_arg, max_n=60):
        return {
            "sample_count": 2,
            "flagged_count": 1,
            "signal_counts": {"scbm_mismatch": 1, "red_invoice": 1},
        }

    monkeypatch.setattr(fraud_engine, "analyze_metrics_batch", _fake_batch)

    spec_kpis = [
        {"label": "舞弊信号数", "metric": "fraud_signal_count", "unit": "项", "source": "fraud"},
        {"label": "可疑主体占比", "metric": "suspicious_ratio", "unit": "%", "source": "fraud"},
        {"label": "进销错配主体占比", "metric": "scbm_mismatch_rate", "unit": "%", "source": "fraud"},
        {"label": "红字异常主体占比", "metric": "red_anomaly_ratio", "unit": "%", "source": "fraud"},
    ]
    resolved = await _resolve_scenario_kpis(None, spec_kpis, {"avg_score": None})
    by_metric = {k["metric"]: k for k in resolved}

    assert by_metric["fraud_signal_count"]["value"] == "2"      # 1+1 信号实例
    assert by_metric["suspicious_ratio"]["value"] == "50.0"      # 1/2 可疑主体
    assert by_metric["scbm_mismatch_rate"]["value"] == "50.0"   # 1/2 进销错配
    assert by_metric["red_anomaly_ratio"]["value"] == "50.0"    # 1/2 红字异常
    assert by_metric["fraud_signal_count"]["trace"] == "fraud.fraud_signal_count"


def test_build_report_detail_slice():
    """切片快照 → 结构化详情：kpis 带 source，章节结论=声明串联，证据链可回溯。"""
    snap = {
        "scenario": "tax",
        "title": "税务合规体检报告",
        "subtitle": "匿名切片",
        "report_date": "2026年08月29日",
        "summary_kpis": [
            {"label": "纳税准时率", "value": "85.0", "unit": "%", "source": "core_metrics", "trace": "core_metrics.tax_on_time_rate"},
        ],
        "executive_summary": "样本整体合规。",
        "chapters": [
            {
                "title": "税务趋势",
                "purpose": "p1",
                "claims": [
                    {"claim": "准时率 85%。", "trace": {"table": "core_metrics", "field": "tax_on_time_rate"}},
                ],
            }
        ],
    }
    d = build_report_detail("slice_tax_001", snap)
    assert d["id"] == "slice_tax_001"
    assert d["scenario"] == "tax"
    assert d["summary"] == "样本整体合规。"
    assert d["kpis"][0]["source"] == "core_metrics"
    assert d["kpis"][0]["trace"] == "core_metrics.tax_on_time_rate"
    assert d["chapters"][0]["title"] == "税务趋势"
    assert d["chapters"][0]["conclusion"] == "准时率 85%。"
    assert d["chapters"][0]["evidence_chain"] == ["core_metrics.tax_on_time_rate"]
    # 无 validation 快照 → 空 dict（弃权，不伪造 ok）
    assert d["validation"] == {}


def test_build_report_detail_enterprise():
    """企业快照无 chapters → 合成 overall/dimensions/dupont 章节 + 整体 KPI。"""
    snap = {
        "scenario": "enterprise",
        "scenario_label": "企业财务分析报告",
        "title": "企业财务分析报告 · #ab12",
        "report_date": "2026年08月29日",
        "overall": {
            "health": "健康",
            "risk_level": "低风险",
            "overall_score": 85.5,
            "reason": "综合经营表现稳健。",
            "risk_points": ["p1"],
            "advantages": ["a1"],
            "advice": ["c1"],
        },
        "dimensions": [
            {"key": "profit", "title": "盈利能力", "analysis": "盈利稳健", "risk_level": "低", "metrics": []},
        ],
        "dupont": {"formula": "ROE = 净利率 × 周转率 × 权益乘数"},
    }
    d = build_report_detail("ent_ab12_x", snap)
    assert d["scenario"] == "enterprise"
    # 封面 KPI：综合经营表现/风险等级/财务健康
    assert [k["label"] for k in d["kpis"]] == ["综合经营表现", "风险等级", "财务健康"]
    assert d["kpis"][0]["value"] == "稳健"
    assert d["kpis"][1]["value"] == "低风险"
    titles = [c["title"] for c in d["chapters"]]
    assert "总体风险评估" in titles
    assert "盈利能力" in titles
    assert "杜邦分解" in titles
    overall_ch = next(c for c in d["chapters"] if c["id"] == "overall")
    assert overall_ch["points"] == ["p1"]
    assert overall_ch["advantages"] == ["a1"]
    assert overall_ch["advice"] == ["c1"]


def test_build_report_detail_abstain_missing_score():
    """企业无评分 → 综合评分弃权「—」，不伪造。"""
    snap = {
        "scenario": "enterprise",
        "title": "x",
        "report_date": "",
        "overall": {"risk_level": None, "health": None, "overall_score": None, "reason": ""},
        "dimensions": [],
        "dupont": None,
    }
    d = build_report_detail("ent_x", snap)
    assert d["kpis"][0]["value"] == "—"
    assert d["kpis"][1]["value"] == "—"
