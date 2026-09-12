"""规范书禁词 / 聚合字段隔离契约（CI）。"""
from __future__ import annotations

from app.services import hallucination_guard as hg
from app.services.report_templates import FORBIDDEN_MARKERS, scan_forbidden_in_text


def test_forbidden_markers_centralized():
    assert "综合评分" in FORBIDDEN_MARKERS
    assert "Benford" in FORBIDDEN_MARKERS
    assert "本福特定律" not in FORBIDDEN_MARKERS  # 中文映射允许
    assert scan_forbidden_in_text("综合评分 80 分") == ["综合评分"]
    assert scan_forbidden_in_text("T-01 触发") == ["T-01"]
    assert scan_forbidden_in_text("本福特定律符合") == []
    assert scan_forbidden_in_text("综合经营表现「良好」") == []


def test_aggregate_rejects_subject_labels():
    ctx = {
        "story": "样本经营稳健。",
        "summary_kpis": [{"label": "风险等级", "value": "中等"}],
        "chapters": [],
    }
    lex = hg.validate_surface_lexicon(ctx, report_kind="slice")
    assert lex["ok"] is False
    assert any(d["hit"] == "风险等级" for d in lex["details"])


def test_enterprise_allows_risk_level_kpi():
    ctx = {
        "story": "综合经营表现「良好」。",
        "summary_kpis": [{"label": "风险等级", "value": "中等风险"}],
        "overall": {"risk_level": "中等风险", "outlook": "稳定"},
        "chapters": [],
    }
    lex = hg.validate_surface_lexicon(ctx, report_kind="enterprise")
    assert lex["ok"] is True


def test_forbidden_marker_fails_lexicon():
    ctx = {
        "story": "本批综合评分偏高。",
        "summary_kpis": [],
        "chapters": [],
    }
    lex = hg.validate_surface_lexicon(ctx, report_kind="slice")
    assert lex["ok"] is False
    assert any(d["hit"] == "综合评分" for d in lex["details"])
