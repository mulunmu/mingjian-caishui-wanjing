"""切片报告 + 抗幻觉校验"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services import conclusion_store, hallucination_guard
from app.services.report_templates import resolve_scenario, get_scenario
from app.services.slice_report import _chapter_claims, _fallback_executive_summary


def test_resolve_scenario_general():
    assert resolve_scenario(query="生成行业趋势风控报告") == "general"
    assert resolve_scenario(query="欺诈报告") == "fraud"


def test_resolve_scenario_rejects_unknown_explicit():
    with pytest.raises(ValueError, match="未知报告场景"):
        resolve_scenario(scenario="typo_scenario")


def test_scenario_has_chapters():
    spec = get_scenario("general")
    assert spec["title"]
    assert len(spec["chapters"]) >= 3


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
    assert "行业趋势" in s
