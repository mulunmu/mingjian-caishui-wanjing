"""A.3 跨面数字机检契约（CI fixture）：KPI/story/摘要 ⊆ claim∪溯源 KPI。"""
from __future__ import annotations

from app.services import hallucination_guard as hg


def test_a3_unaligned_kpi_blanked_traced_kept():
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
        {"label": "对齐", "value": "5", "unit": "%"},
        {"label": "幽灵", "value": "99.9", "unit": "%"},
        {
            "label": "溯源样本",
            "value": "193",
            "unit": "家",
            "metric": "sample_count",
            "source": "assessment",
        },
    ]
    aligned, stats = hg.enforce_kpi_claim_alignment(kpis, chapters)
    assert stats["blanked_kpis"] == 1
    assert aligned[0]["value"] == "5"
    assert aligned[1]["value"] == "—"
    assert aligned[2]["value"] == "193"


def test_a3_enforce_then_validate_cross_ok():
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
        {"label": "幽灵", "value": "99.9", "unit": "%"},
        {"label": "样本", "value": "12", "unit": "家", "metric": "sample_count", "source": "assessment"},
    ]
    story = "制造行业同比 5%。另有逾期率 99.9%。"
    exec_sum = "样本 12 家，同比 5%。"
    aligned, new_story, new_exec, enf = hg.enforce_cross_surface(
        chapters=chapters,
        summary_kpis=kpis,
        story=story,
        executive_summary=exec_sum,
    )
    assert enf["blanked_kpis"] == 1
    assert "99.9" not in new_story
    assert "5" in new_story
    cross = hg.validate_cross_surface(
        chapters=chapters,
        summary_kpis=aligned,
        story=new_story,
        executive_summary=new_exec,
    )
    assert cross["ok"] is True
    assert cross["kpi_unaligned"] == 0
    assert cross["text_unanchored"] == 0


def test_a3_validate_detects_before_enforce():
    chapters = [
        {
            "title": "趋势",
            "claims": [
                {
                    "claim": "同比 5%。",
                    "confidence": "computed",
                    "value": {"metric": "yoy", "number": 5.0, "unit": "%"},
                    "trace": {"table": "core_metrics", "field": "yoy", "query_id": "Q1"},
                }
            ],
        }
    ]
    cross = hg.validate_cross_surface(
        chapters=chapters,
        summary_kpis=[{"label": "x", "value": "99.9", "unit": "%"}],
        story="逾期率 99.9%。",
        executive_summary="幽灵 88%。",
    )
    assert cross["ok"] is False
    assert cross["kpi_unaligned"] >= 1
    assert cross["text_unanchored"] >= 1
