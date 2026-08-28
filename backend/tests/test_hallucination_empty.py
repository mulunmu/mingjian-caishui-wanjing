"""空章节不得标「抗幻觉通过」。"""
from app.services.hallucination_guard import validate_report_chapters


def test_empty_chapters_fail_guard():
    out = validate_report_chapters([])
    assert out["ok"] is False
    assert out["empty"] is True
    assert out["total_claims"] == 0


def test_empty_claims_in_chapter_fail():
    out = validate_report_chapters([{"title": "空", "claims": []}])
    assert out["ok"] is False
    assert out["empty"] is True
