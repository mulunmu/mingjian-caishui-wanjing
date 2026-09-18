from __future__ import annotations

from app.services.report_blocks import (
    dedupe_report_blocks_across_chapters,
    normalize_report_block,
    report_block_fingerprint,
)


def test_semantic_fingerprint_is_stable_for_same_claim():
    left = {"type": "metric_paragraph", "metric": "overall_score", "number": 82, "unit": "分", "paragraph": "经营表现中等。"}
    right = {"type": "metric_paragraph", "metric": "overall_score", "number": 82, "unit": "分", "paragraph": "经营表现中等。"}
    assert report_block_fingerprint(left) == report_block_fingerprint(right)


def test_cross_chapter_duplicate_is_marked_not_copied():
    chapters = [
        {
            "function": "score",
            "blocks": [
                normalize_report_block(
                    {"type": "metric_paragraph", "metric": "overall_score", "number": 82, "unit": "分", "paragraph": "经营表现中等。"},
                    chapter_key="score",
                    index=0,
                )
            ],
        },
        {
            "function": "benchmark",
            "blocks": [
                normalize_report_block(
                    {"type": "metric_paragraph", "metric": "overall_score", "number": 82, "unit": "分", "paragraph": "经营表现中等。"},
                    chapter_key="benchmark",
                    index=0,
                )
            ],
        },
    ]
    owners = dedupe_report_blocks_across_chapters(chapters)
    assert len(owners) == 1
    assert chapters[0]["blocks"][0]["status"] == "active"
    assert chapters[1]["blocks"][0]["status"] == "duplicate"
    assert chapters[1]["blocks"][0]["duplicate_of"] == chapters[0]["blocks"][0]["block_id"]
