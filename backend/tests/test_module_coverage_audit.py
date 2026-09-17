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
    assert summary["registry_metrics_total"] == summary["metrics_total"]
    assert summary["metrics_planned"] == 48
    assert summary["metrics_validated"] == 53
    assert summary["metrics_executable"] == 53
    assert summary["validated_metrics_with_aliases"] == 53
    assert len(summary["planned_metric_keys"]) == 48
    assert summary["tools_total"] >= summary["metrics_total"]
    assert summary["metric_tools_validated"] == 53
    assert summary["chapter_tools_validated"] == 8
    assert summary["chapters_total"] >= 8
    assert summary["metrics_executable"] >= 40
    assert summary["chapter_gaps"] == []
    assert summary["thresholds_missing_required"] == []
    assert summary["validated_missing_surface_label"] == []
    assert summary["composition"]["metric_to_chapter_pairs"] > 0
    assert summary["composition"]["missing_metric_to_chapter"] == []
    assert summary["composition"]["metric_pair_to_chapter_triples"] > 0
    assert summary["composition"]["missing_metric_pair_to_chapter"] == []
    assert summary["report_blocks"]["compatible_pair_count"] >= 30
    assert summary["report_blocks"]["missing"] == []
    assert len(report["metrics"]) == summary["metrics_total"]
    assert any(item["metric_key"] == "debt_ratio" for item in report["metrics"])
