from __future__ import annotations

from scripts.run_stage14_report_block_matrix import run


def test_stage14_report_block_matrix_has_no_failures():
    report = run()
    assert report["total"] >= 30
    assert report["passed"] == report["total"]
    assert report["failed"] == 0
    assert report["failures"] == []
