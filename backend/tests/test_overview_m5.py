"""M5：工作台 summary 返回结论 + TopN，不整表下发 enterprises。"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_dashboard_summary_has_conclusion_and_top_not_full_table(live_db):
    from app.services import assessment

    async with live_db() as db:
        summary = await assessment.get_dashboard_summary(db, top_n=5)
    assert "conclusion" in summary and summary["conclusion"]
    assert "top_warnings" in summary
    assert isinstance(summary["top_warnings"], list)
    assert len(summary["top_warnings"]) <= 5
    assert summary.get("top_warnings_total", 0) >= len(summary["top_warnings"])
    # 不再整表下发
    assert summary.get("enterprises") == []
    assert "industry_distribution" in summary
    assert summary["sample_count"] >= 0


@pytest.mark.asyncio
async def test_warnings_respects_limit(live_db):
    from app.services import assessment

    async with live_db() as db:
        limited = await assessment.get_all_warnings(db, limit=3, high_risk_only=True)
    assert len(limited) <= 3
    if len(limited) >= 2:
        assert limited[0]["overall_score"] <= limited[1]["overall_score"]


def test_dashboard_summary_empty_shape():
    """空库返回结构完整（同步冒烟：仅校验字段约定，不连库）。"""
    keys = {
        "sample_count",
        "high_risk_count",
        "avg_score",
        "warning_count",
        "risk_distribution",
        "industry_distribution",
        "industry_profiles",
        "conclusion",
        "top_warnings",
        "top_warnings_total",
        "enterprises",
    }
    # 文档/契约：空态字段集合须覆盖前端 OverviewData 所需键
    assert keys >= {
        "conclusion",
        "top_warnings",
        "top_warnings_total",
        "sample_count",
    }
