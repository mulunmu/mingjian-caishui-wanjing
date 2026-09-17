from __future__ import annotations

try:
    from scripts.eval_report_plan import build_report_eval_specs
except ImportError:
    from backend.scripts.eval_report_plan import build_report_eval_specs


def test_report_eval_contains_multi_chapter_combinations():
    specs = build_report_eval_specs()

    assert len(specs) >= 30
    assert any(len(spec.chapters) >= 2 for spec in specs)
    assert any(len(spec.chapters) >= 4 for spec in specs)
    assert all(spec.chapters for spec in specs)
