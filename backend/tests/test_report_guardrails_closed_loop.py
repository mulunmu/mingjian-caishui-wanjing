"""四层防护闭环 · 边界自动化用例（不依赖人工看 PDF）。"""
from __future__ import annotations

import pytest

from app.services import report_preflight as pf
from app.services.scope_contract import validate_firm_counts_within_scope


def test_firm_count_over_sample_blocks_preflight():
    ctx = {
        "scenario": "due_diligence",
        "period_count": 1,
        "attribution": {
            "sample_count": 19,
            "drag_factors": [{"item": "税务违法", "count": 26}],
            "summary": "建筑行业群体风险判断「中高风险」。",
        },
        "summary_risks": ["税务违法（26 家）"],
        "summary_strengths": [],
        "summary_conclusion": "群体风险判断中高风险",
        "executive_summary": "样本有限，统计结果仅供参考。",
        "cover_meta": {
            "sample_count": "19",
            "small_sample": True,
            "small_sample_banner": "当前统计子集仅 19 家，样本有限，统计结果仅供参考。",
        },
        "chapters": [
            {
                "title": "x",
                "claims": [
                    {
                        "claim": "样本 19 家。",
                        "value": {"metric": "sample_count", "number": 19, "unit": "家"},
                        "trace": {"table": "t", "field": "f", "query_id": "Q1"},
                        "confidence": "computed",
                    }
                ],
                "meta": {"sample_count": 19},
            }
        ],
        "validation": {"empty": False, "total_claims": 1, "ok": True},
    }
    result = pf.run_preflight(ctx)
    assert result["ok"] is False
    assert "firm_count_guard" in result["hard_blocks"]


def test_firm_count_within_sample_passes_guard():
    g = validate_firm_counts_within_scope(
        scope_sample_count=59,
        drag_factors=[{"item": "税务违法", "count": 48}],
        summary_risks=["税务违法（48 家 / 样本 59 家）"],
    )
    assert g["ok"] is True


def test_equity_invalid_metric_blocked_from_advantages():
    ctx = {
        "scenario": "enterprise",
        "period_count": 1,
        "overall": {
            "advantages": ["净资产收益率 120%，达标", "计算失效（权益为负，不予采信）"],
            "risk_points": ["所有者权益为负"],
            "advice": ["核对报表"],
        },
        "six_dimensions": [{"key": "finance"}],
        "radar_dims": ["finance"],
        "validation": {"empty": False, "total_claims": 2, "ok": True},
    }
    result = pf.run_preflight(ctx)
    assert result["ok"] is False
    assert "equity_rules" in result["hard_blocks"]


def test_temporal_word_blocked_on_single_period():
    ctx = {
        "scenario": "enterprise",
        "period_count": 1,
        "overall": {
            "reason": "盈利持续恶化，风险上升。",
            "advantages": ["毛利率达标"],
            "risk_points": ["净利率预警"],
            "advice": ["核查"],
        },
        "story": "盈利持续恶化。",
        "six_dimensions": [{"key": "finance"}],
        "radar_dims": ["finance"],
        "validation": {"empty": False, "total_claims": 2, "ok": True},
    }
    result = pf.run_preflight(ctx)
    assert result["ok"] is False
    assert "temporal" in result["hard_blocks"]


def test_temporal_allows_going_concern_phrase():
    ctx = {
        "scenario": "enterprise",
        "period_count": 1,
        "overall": {
            "reason": "建议关注持续经营能力。",
            "advantages": ["毛利率达标"],
            "risk_points": ["营收下滑"],
            "advice": ["核查持续经营能力"],
        },
        "story": "建议关注持续经营能力。",
        "six_dimensions": [{"key": "finance"}],
        "radar_dims": ["finance"],
        "validation": {"empty": False, "total_claims": 2, "ok": True},
    }
    # 仅「持续经营」不应触发；若 lexicon 等其他项失败另论
    temporal = pf.validate_temporal_gate(ctx)
    assert temporal["ok"] is True


def test_radar_subset_mismatch_blocks():
    ctx = {
        "scenario": "enterprise",
        "period_count": 1,
        "overall": {
            "reason": "评级中等。",
            "advantages": ["毛利率达标"],
            "risk_points": ["流动比率偏低"],
            "advice": ["核查"],
        },
        "six_dimensions": [{"key": "finance"}],
        "radar_dims": ["finance", "legal"],
        "validation": {
            "empty": False,
            "total_claims": 2,
            "ok": True,
            "radar_subset": {
                "ok": False,
                "extra_in_radar": ["legal"],
            },
        },
    }
    result = pf.run_preflight(ctx)
    assert result["ok"] is False
    assert "radar_subset" in result["hard_blocks"]


def test_aggregate_inferred_marker_blocked():
    ctx = {
        "scenario": "due_diligence",
        "period_count": 1,
        "attribution": {"sample_count": 59, "drag_factors": [], "summary": "群体中等。"},
        "summary_risks": ["税务违法（10 家 / 样本 59 家）"],
        "summary_strengths": [],
        "summary_conclusion": "中等",
        "executive_summary": "[据推断] 风险可能上升。",
        "cover_meta": {"sample_count": "59"},
        "chapters": [
            {
                "title": "税务",
                "claims": [
                    {
                        "claim": "税务违法 10 家。",
                        "value": {"number": 10, "unit": "家", "metric": "tax"},
                        "trace": {"table": "t", "field": "f", "query_id": "Q"},
                        "confidence": "computed",
                    }
                ],
                "meta": {"sample_count": 59},
            }
        ],
        "validation": {"empty": False, "total_claims": 1, "ok": True},
    }
    result = pf.run_preflight(ctx)
    assert result["ok"] is False
    assert "no_inference" in result["hard_blocks"]


def test_small_sample_requires_banner():
    ctx = {
        "scenario": "due_diligence",
        "period_count": 1,
        "attribution": {"sample_count": 12, "drag_factors": [], "summary": "样本偏少。"},
        "summary_risks": [],
        "summary_strengths": [],
        "summary_conclusion": "样本 12 家",
        "executive_summary": "样本 12 家完成统计。",
        "cover_meta": {"sample_count": "12", "small_sample": True},
        "chapters": [
            {
                "title": "x",
                "claims": [
                    {
                        "claim": "样本 12 家。",
                        "value": {"number": 12, "unit": "家", "metric": "n"},
                        "trace": {"table": "t", "field": "f", "query_id": "Q"},
                        "confidence": "computed",
                    }
                ],
                "meta": {"sample_count": 12},
            }
        ],
        "validation": {"empty": False, "total_claims": 1, "ok": True},
    }
    result = pf.run_preflight(ctx)
    assert result["ok"] is False
    assert "small_sample" in result["hard_blocks"]


def test_assert_renderable_raises_on_bad_context():
    ctx = {
        "scenario": "due_diligence",
        "period_count": 1,
        "attribution": {
            "sample_count": 10,
            "drag_factors": [{"item": "税务违法", "count": 99}],
            "summary": "x",
        },
        "summary_risks": ["税务违法（99 家）"],
        "cover_meta": {
            "sample_count": "10",
            "small_sample_banner": "当前统计子集仅 10 家，样本有限，统计结果仅供参考。",
        },
        "executive_summary": "样本有限，统计结果仅供参考。",
        "chapters": [
            {
                "title": "x",
                "claims": [
                    {
                        "claim": "样本 10 家。",
                        "value": {"number": 10, "unit": "家", "metric": "n"},
                        "trace": {"table": "t", "field": "f", "query_id": "Q"},
                        "confidence": "computed",
                    }
                ],
                "meta": {"sample_count": 10},
            }
        ],
        "validation": {"empty": False, "total_claims": 1, "ok": True},
    }
    with pytest.raises(ValueError, match="预校验未通过"):
        pf.assert_renderable_or_raise(ctx)


def test_html_postflight_blocks_inferred_and_subject_fields():
    ctx = {
        "scenario": "due_diligence",
        "period_count": 1,
        "attribution": {"sample_count": 59},
        "summary_risks": ["税务违法（10 家 / 样本 59 家）"],
        "cover_meta": {"sample_count": "59"},
        "validation": {"total_claims": 1},
    }
    html = "<html><body>风险等级：高风险 评级展望：负面 [据推断] 可能恶化 样本 59 家 税务违法 10 家</body></html>"
    post = pf.run_postflight_html(html, ctx)
    assert post["ok"] is False
    reasons = {h.get("reason") for h in (post.get("html") or {}).get("hard") or []}
    assert "inferred_in_html" in reasons or "subject_field_in_aggregate_html" in reasons


def test_summary_bullets_reject_empty():
    ctx = {
        "scenario": "enterprise",
        "period_count": 1,
        "overall": {
            "advantages": ["毛利率达标"],
            "risk_points": [""],
            "advice": ["核查"],
        },
        "six_dimensions": [{"key": "finance"}],
        "radar_dims": ["finance"],
        "validation": {"empty": False, "total_claims": 1, "ok": True},
    }
    result = pf.run_preflight(ctx)
    assert result["ok"] is False
    assert "summary_bullets" in result["hard_blocks"]


def test_enterprise_rule_analysis_not_flagged_as_llm_narration():
    """规则引擎维度解读升格为 claim，不应再因 narration 触发数字/方向 soft。"""
    from app.services.report_preflight import run_preflight
    from app.services.slice_report import _enterprise_chapters_for_validation
    from app.services import hallucination_guard as hg

    dims = [
        {
            "key": "authenticity",
            "title": "经营真实性",
            "metrics": [
                {
                    "label": "本维指数",
                    "value": "61.1",
                    "unit": "",
                    "standard": "≥60",
                    "rating": "达标",
                }
            ],
            "analysis": {
                "level_review": "「经营真实性」本维指数 61.1，风险等级「低」。",
                "trend": "",
                "risks": "多源交叉验证可疑（交叉验证可疑=是，交叉偏差率 29.5%）",
                "advice": "建议核实申报数据。",
            },
        }
    ]
    chapters = _enterprise_chapters_for_validation(
        dimensions=dims,
        risk_points=["多源交叉验证可疑：交叉偏差率 29.5%"],
        reason="经营真实性承压。",
        overall_score=50.0,
    )
    val = hg.validate_report_chapters(chapters)
    assert val["number_unanchored"] == 0
    assert val["risk_contradictions"] == 0
    assert all(not (ch.get("narration") or "").strip() for ch in chapters)


def test_fmt_firm_count_includes_sample_base():
    from app.services.slice_report import _fmt_firm_count, _tax_signals

    assert _fmt_firm_count("欠税主体", 11, 59) == "欠税主体 11 家 / 样本 59 家（18.6%）"
    strengths, risks = _tax_signals(
        [],
        {"sample_count": 59, "arrears_cnt": 11, "violation_cnt": 22, "on_time_avg": 0.776},
    )
    assert any("样本 59 家" in r for r in risks)
    assert strengths == []


def test_yoy_not_listed_as_advantage():
    from types import SimpleNamespace

    from app.services.slice_report import _collect_advantages

    fin = SimpleNamespace(
        owner_equity=100,
        debt_ratio=0.5,
        current_ratio=1.5,
        quick_ratio=1.0,
        receivables_turnover=3.0,
        inventory_turnover=3.0,
        gross_margin=0.2,
        net_margin=0.05,
        roe=0.1,
        revenue_yoy=-0.059,
        profit_yoy=-0.1,
    )
    adv = _collect_advantages({"credit_level": "C"}, fin)
    assert not any("同比" in a for a in adv)


def test_profit_yoy_warns_on_steep_drop():
    from app.services.financial_benchmarks import assess_financial_ratio

    assert assess_financial_ratio("profit_yoy", -0.973) == "预警"
    assert assess_financial_ratio("profit_yoy", -0.05) == "达标"


def test_chapter_conclusion_prefers_action_over_table_echo():
    from app.services.report_templates import chapter_conclusion_lines

    lines = chapter_conclusion_lines(
        {
            "narration": "纳税准时率均值 73.6%，增值税税负率均值 2.44%。",
            "numeric_rows": [["纳税准时率", "73.6", "%", "x"]],
            "claims": [
                {"claim": "纳税准时率均值 73.6%。"},
                {"claim": "税务违法主体偏多，建议优先核查欠税与违法记录。"},
            ],
        }
    )
    assert lines
    assert any("建议" in x for x in lines)
    assert not any(x.startswith("纳税准时率均值 73.6%") and "建议" not in x for x in lines)


def test_dedupe_chapter_yoy_hint():
    from app.services.slice_report import _dedupe_chapter_surface_text

    chapters = [
        {
            "sample_note": "统计子集 19 家；样本偏少，统计结果仅供参考",
            "narration": "统计子集 19 家；样本偏少，统计结果仅供参考。税务违法主体偏多，建议优先核查。已纳入同比类指标解读。",
        }
    ]
    _dedupe_chapter_surface_text(chapters)
    nar = chapters[0]["narration"]
    assert "样本偏少" not in nar
    assert "已纳入同比" not in nar
    assert "建议优先核查" in nar
