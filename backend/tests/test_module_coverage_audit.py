from __future__ import annotations

from app.services.semantic_registry_seed import seed_semantic_registry
from scripts.audit_module_coverage import build_coverage_report
from tests.test_semantic_registry_seed import _engine


def test_module_coverage_audit_builds_metric_tool_and_chapter_summary():
    engine = _engine()
    seed_semantic_registry(engine)

    report = build_coverage_report(engine)
    summary = report["summary"]

    assert summary["metrics_total"] >= 60
    assert summary["tools_total"] >= summary["metrics_total"]
    assert summary["chapters_total"] >= 8
    assert summary["metrics_executable"] >= 40
    assert "chapter_gaps" in summary
    assert len(report["metrics"]) == summary["metrics_total"]
    assert any(item["metric_key"] == "debt_ratio" for item in report["metrics"])
