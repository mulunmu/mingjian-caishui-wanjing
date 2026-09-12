"""向导预校验与 lexicon：画像副标题不得含禁词「分位」。"""
from __future__ import annotations

from app.services.report_templates import (
    get_scenario,
    sanitize_surface_industry_terms,
    scan_forbidden_in_text,
)


def test_portrait_subtitle_has_no_forbidden_fenwei():
    spec = get_scenario("portrait")
    assert "分位" not in (spec.get("subtitle") or "")
    assert scan_forbidden_in_text(spec.get("subtitle") or "") == []
    assert scan_forbidden_in_text(spec.get("title") or "") == []


def test_sanitize_strips_fenwei_residue():
    assert "分位" not in sanitize_surface_industry_terms("结构分布 · 均值分位 · 信用")
    assert "分布" in sanitize_surface_industry_terms("结构分布 · 均值分位 · 信用")
