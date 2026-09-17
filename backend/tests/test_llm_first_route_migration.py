from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _run_audit() -> dict:
    completed = subprocess.run(
        [sys.executable, "scripts/audit_llm_first_migration.py"],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_audit_reports_current_llm_first_migration_gaps():
    report = _run_audit()

    assert report["status"] == "migration_required"
    assert report["route_derived_from_plan"] is False
    assert report["planner_in_langgraph_node"] is True
    assert report["report_plan_enabled"] is False
    assert report["legacy_fallback_isolated"] is False

    symbols = {
        (item["file"], item["symbol"])
        for item in report["semantic_overrides"]
    }
    assert ("services/semantic_frame.py", "_OPEN_OVERVIEW_RE") in symbols
    assert ("services/semantic_primary.py", "_PATTERN_CANDIDATE_PRIORITY") in symbols


def test_audit_is_json_serializable_and_has_explicit_counts():
    report = _run_audit()

    assert isinstance(report["semantic_overrides"], list)
    assert report["counts"]["semantic_overrides"] == len(report["semantic_overrides"])
    assert report["counts"]["semantic_overrides"] > 0
