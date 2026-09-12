"""P0 机制契约：雷达⊆章节、中文指标、时序词、计数整数。"""
from __future__ import annotations

from app.services import hallucination_guard as hg
from app.services.chart_payloads import enterprise_radar_chart
from app.services.metric_registry import format_surface_number, zh_metric_label
from app.services.report_templates import chapter_conclusion_lines
from app.services.slice_report import _numeric_table_rows


def test_zh_metric_label_maps_financial_fields():
    assert zh_metric_label("financial_coverage") == "财务覆盖率"
    assert zh_metric_label("current_ratio") == "流动比率"
    assert zh_metric_label("quick_ratio") == "速动比率"
    assert zh_metric_label("unknown_snake_case") is None


def test_numeric_rows_never_emit_english_metric():
    claims = [
        {
            "claim": "覆盖 12 家。",
            "value": {"metric": "financial_coverage", "number": 12, "unit": "家"},
        },
        {
            "claim": "幽灵字段",
            "value": {"metric": "totally_unknown_field_xyz", "number": 1.5, "unit": ""},
        },
        {
            "claim": "流动比率均值 1.2。",
            "value": {"metric": "current_ratio", "number": 1.2, "unit": ""},
        },
    ]
    rows = _numeric_table_rows(claims)
    labels = [r[0] for r in rows]
    assert "财务覆盖率" in labels
    assert "流动比率" in labels
    assert all("_" not in r[0] for r in rows)
    assert all(r[0].isascii() is False or any("\u4e00" <= c <= "\u9fff" for c in r[0]) for r in rows)


def test_format_count_as_integer():
    assert format_surface_number(2.0, "项") == "2"
    assert format_surface_number(2.00, "家") == "2"


def test_enterprise_radar_cropped_to_dims():
    ent = {
        "dimensions": {
            "tax_health": 70,
            "authenticity": 25.7,
            "invoice": 55,
            "industry": 60,
            "legal": 80,
            "finance": 50,
        },
        "display_label": "样本",
    }
    chart = enterprise_radar_chart(ent, dims=["finance", "authenticity"])
    assert chart is not None
    names = [i["name"] for i in chart["data"]["indicators"]]
    assert "经营真实性" in names
    assert "财务健康" in names
    assert "税务健康" not in names


def test_radar_subset_validation():
    ok = hg.validate_radar_subset_of_chapters(
        radar_dims=["finance", "authenticity"],
        chapter_dim_keys=["finance", "authenticity", "tax_health"],
    )
    assert ok["ok"] is True
    bad = hg.validate_radar_subset_of_chapters(
        radar_dims=["finance", "legal"],
        chapter_dim_keys=["finance"],
    )
    assert bad["ok"] is False
    assert "legal" in bad["extra_in_radar"]


def test_scrub_temporal_words():
    assert "持续" not in hg.scrub_temporal_words("净利率-21.4%持续亏损")
    assert "亏损" in hg.scrub_temporal_words("净利率-21.4%持续亏损")
    assert "持续经营" in hg.scrub_temporal_words("关注持续经营能力")


def test_chapter_conclusion_does_not_dump_table():
    ch = {
        "narration": "",
        "numeric_rows": [["流动比率", "1.2", "", "x"]],
        "claims": [
            {"claim": "流动比率均值 1.2（达标，样本 10）。", "confidence": "computed"},
            {"claim": "样本整体偿债承压，建议关注流动性。", "confidence": "computed"},
        ],
    }
    lines = chapter_conclusion_lines(ch)
    assert len(lines) <= 3
    assert any("承压" in x or "建议" in x for x in lines)


def test_anomalous_financial_not_pass():
    from app.services.financial_benchmarks import assess_financial_ratio, is_anomalous_amount

    assert assess_financial_ratio("debt_ratio", -2.0) == "账务异常"
    assert assess_financial_ratio("current_ratio", -0.5) == "账务异常"
    assert assess_financial_ratio("debt_ratio", 0.5) == "达标"
    assert is_anomalous_amount("total_liab", -205.19) is True
    assert is_anomalous_amount("total_liab", 100.0) is False


def test_scope_sample_alignment_blocks_full_reuse():
    from app.services.scope_contract import validate_scope_sample_alignment

    chapters = [
        {"title": "税务风险信号", "function": "signal", "meta": {"sample_count": 193}},
        {"title": "财务健康", "function": "financial", "meta": {"sample_count": 45}},
    ]
    bad = validate_scope_sample_alignment(
        chapters, scope_sample_count=60, industry_l1="制造"
    )
    assert bad["ok"] is False
    assert any(m["function"] == "signal" for m in bad["mismatches"])

    ok = validate_scope_sample_alignment(
        [
            {"title": "税务风险信号", "function": "signal", "meta": {"sample_count": 60}},
            {"title": "财务健康", "function": "financial", "meta": {"sample_count": 45}},
        ],
        scope_sample_count=60,
        industry_l1="制造",
    )
    assert ok["ok"] is True


def test_firm_count_guard_blocks_over_sample():
    from app.services.scope_contract import validate_firm_counts_within_scope

    bad = validate_firm_counts_within_scope(
        scope_sample_count=19,
        drag_factors=[{"item": "税务违法", "count": 26}],
        summary_risks=["税务违法（26 家）"],
    )
    assert bad["ok"] is False
    assert any(v["count"] == 26 for v in bad["violations"])

    ok = validate_firm_counts_within_scope(
        scope_sample_count=19,
        drag_factors=[{"item": "税务违法", "count": 13}],
        summary_risks=["税务违法（13 家 / 样本 19 家）"],
    )
    assert ok["ok"] is True


def test_finalize_summary_bullets_never_mid_truncate():
    from app.services.slice_report import _finalize_summary_bullets

    long = "多重风险叠加：高危信号数 4项，叠加项=存在欠税、税务违法记录、进销品目错配、多源交叉验证可疑"
    out = _finalize_summary_bullets([long, long, "短条"], limit=8)
    assert out[0] == long
    assert len(out) == 2


def test_chapter_conclusion_no_inferred_prefix():
    from app.services.report_templates import chapter_conclusion_lines

    lines = chapter_conclusion_lines(
        {
            "claims": [
                {
                    "claim": "税务违法主体偏多，建议优先核查。",
                    "confidence": "inferred",
                }
            ],
            "numeric_rows": [["a", "1", "", "x"]],
        }
    )
    assert lines
    assert not any("据推断" in x for x in lines)


def test_sample_note_warns_small_n():
    from app.services.scope_contract import sample_note, small_sample_banner

    note = sample_note({"sample_count": 12})
    assert note is not None
    assert "仅供参考" in note
    big = sample_note({"sample_count": 60})
    assert big is not None
    assert "仅供参考" not in big
    assert small_sample_banner(12) is not None
    assert small_sample_banner(60) is None


def test_six_dim_temporal_note_only_once():
    from app.services.slice_report import _build_six_dim_sections, _six_dim_temporal_note

    profile = {
        "dimensions": {
            "tax_health": 70,
            "authenticity": 25,
            "invoice": 55,
            "industry": 60,
            "legal": 80,
            "finance": 50,
        }
    }
    sections = _build_six_dim_sections(profile, [], has_yoy=True)
    trends = [s["analysis"]["trend"] for s in sections if s["analysis"].get("trend")]
    assert trends == []
    note = _six_dim_temporal_note(has_yoy=True)
    assert "同比" in note
    assert "详见" in note


def test_current_ratio_evidence_not_percent():
    from app.services.insight_engine import Evidence

    e = Evidence("流动比率", 0.88, "", "core_metrics", "current_ratio")
    text = e.render()
    assert "88.0%" not in text
    assert "0.88" in text


def test_roe_invalid_when_equity_negative():
    from app.services.financial_benchmarks import (
        assess_financial_ratio,
        format_financial_ratio,
        is_equity_based_ratio_invalid,
    )

    assert is_equity_based_ratio_invalid("roe", owner_equity=-613633) is True
    assert assess_financial_ratio("roe", 1.5188, owner_equity=-613633) == "计算失效"
    assert format_financial_ratio("roe", 1.5188, owner_equity=-613633) == "—"
    assert assess_financial_ratio("roe", 0.15, owner_equity=100000) == "达标"


def test_benchmark_skips_anomalous_debt_ratio():
    from types import SimpleNamespace
    from app.services.slice_report import _build_benchmark_chart, _benchmark_interpretation

    fin = SimpleNamespace(
        debt_ratio=-2.0,
        gross_margin=0.2,
        net_margin=0.05,
        roe=1.5,
        roa=0.06,
        owner_equity=-1000,
        current_ratio=0,
        quick_ratio=0,
    )
    bench = SimpleNamespace(
        avg_debt_ratio=0.5,
        avg_gross_margin=0.15,
        avg_net_margin=0.04,
        avg_roe=0.08,
        avg_roa=0.05,
    )
    chart = _build_benchmark_chart(fin, True, bench)
    assert chart is not None
    assert "资产负债率" not in chart["data"]["labels"]
    assert "净资产收益率" not in chart["data"]["labels"]
    assert "毛利率" in chart["data"]["labels"]
    text = _benchmark_interpretation(fin, True, bench)
    assert "排除" in text
