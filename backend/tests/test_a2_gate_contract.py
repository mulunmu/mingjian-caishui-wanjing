"""A.2 校验升门禁契约（CI fixture）：锁定空报告拒 PDF、剥离后可过、详情回传 validation。"""
from __future__ import annotations

from app.services import hallucination_guard
from app.services.slice_report import _assert_report_renderable, build_report_detail


def test_a2_empty_rejects_pdf():
    try:
        _assert_report_renderable({"validation": {"empty": True, "total_claims": 0}})
        assert False, "expected ValueError"
    except ValueError as exc:
        msg = str(exc)
        assert "无可溯源" in msg or "empty_or_no_claims" in msg or "预校验未通过" in msg


def test_a2_enforce_then_validate_ok():
    chapters = [
        {
            "title": "偿债",
            "claims": [
                {
                    "claim": "流动比率均值 1.80（达标）。",
                    "confidence": "computed",
                    "value": {"metric": "current_ratio", "number": 1.8, "unit": ""},
                    "trace": {"table": "enterprise_financials", "field": "current_ratio", "query_id": "Q1"},
                },
                {"claim": "编造", "confidence": "asserted"},
            ],
            "narration": "流动比率 1.80 承压。逾期 99.9%。流动比率 1.80 稳健。",
        }
    ]
    enf = hallucination_guard.enforce_chapter_integrity(chapters)
    assert enf["dropped_claims"] >= 1
    v = hallucination_guard.validate_report_chapters(chapters)
    assert v["ok"] is True
    assert v["empty"] is False
    _assert_report_renderable({"validation": v})


def test_a2_detail_exposes_validation_from_snapshot():
    snap = {
        "scenario": "tax",
        "title": "税务合规体检报告",
        "subtitle": "匿名切片",
        "report_date": "2026年08月30日",
        "story": "准时率 85%。",
        "summary_kpis": [],
        "executive_summary": "",
        "chapters": [],
        "validation": {
            "ok": False,
            "empty": False,
            "total_claims": 2,
            "unanchored": 1,
            "number_unanchored": 0,
            "risk_contradictions": 0,
            "details": [{"reason": "asserted"}],
        },
    }
    d = build_report_detail("slice_tax_gate", snap)
    assert d["validation"]["ok"] is False
    assert d["validation"]["unanchored"] == 1
    assert d["story"] == "准时率 85%。"
