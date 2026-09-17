"""Audit semantic-rule debt for the LLM-first migration.

This script intentionally inspects source structure instead of importing the
application. It can therefore run in a minimal environment and report the
migration state before any runtime dependencies are available.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Iterable


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

SEMANTIC_SYMBOLS: dict[str, tuple[str, ...]] = {
    "services/route_normalize.py": (
        "_REPORT_REQUEST_RE",
        "is_industry_distribution_query",
    ),
    "services/semantic_frame.py": (
        "is_industry_distribution_query",
        "_OPEN_OVERVIEW_RE",
        "_COMPARISON_RE",
        "_TREND_RE",
        "_DIAGNOSIS_RE",
        "_DOMAIN_ANALYSIS_RE",
    ),
    "services/semantic_primary.py": (
        "is_industry_distribution_query",
        "_PATTERN_CANDIDATE_PRIORITY",
    ),
}


def _defined_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _scan_symbols() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for relative, symbols in SEMANTIC_SYMBOLS.items():
        path = APP_ROOT / relative
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        defined = _defined_names(tree)
        for symbol in symbols:
            if symbol not in defined:
                continue
            category = (
                "fixed_candidate_priority"
                if symbol == "_PATTERN_CANDIDATE_PRIORITY"
                else "semantic_route_override"
                if "route" in relative or symbol == "is_industry_distribution_query"
                else "semantic_frame_override"
            )
            findings.append(
                {
                    "file": relative,
                    "symbol": symbol,
                    "category": category,
                }
            )
    return sorted(findings, key=lambda item: (item["file"], item["symbol"]))


def _contains(path: Path, needle: str) -> bool:
    if not path.exists():
        return False
    return needle in path.read_text(encoding="utf-8")


def build_report() -> dict:
    overrides = _scan_symbols()
    report_plan_path = APP_ROOT / "schemas" / "report_plan.py"
    report_planner_path = APP_ROOT / "services" / "report_planner.py"
    legacy_fallback_path = APP_ROOT / "services" / "legacy_fallback.py"
    outer_orchestrator = APP_ROOT / "services" / "outer_orchestrator.py"
    semantic_nodes_path = APP_ROOT / "services" / "semantic_nodes.py"

    report = {
        "status": "migration_required",
        "route_derived_from_plan": bool(overrides) is False,
        "planner_in_langgraph_node": _contains(
            outer_orchestrator, "semantic_nodes.semantic_planner_node"
        )
        or _contains(semantic_nodes_path, "plan_semantic_turn"),
        "report_plan_enabled": report_plan_path.exists()
        and report_planner_path.exists(),
        "legacy_fallback_isolated": legacy_fallback_path.exists(),
        "semantic_overrides": overrides,
        "counts": {
            "semantic_overrides": len(overrides),
            "route_override_symbols": sum(
                1 for item in overrides if item["category"] == "semantic_route_override"
            ),
            "frame_override_symbols": sum(
                1 for item in overrides if item["category"] == "semantic_frame_override"
            ),
            "fixed_priority_symbols": sum(
                1 for item in overrides if item["category"] == "fixed_candidate_priority"
            ),
        },
    }
    if (
        report["route_derived_from_plan"]
        and report["planner_in_langgraph_node"]
        and report["report_plan_enabled"]
        and report["legacy_fallback_isolated"]
    ):
        report["status"] = "complete"
    return report


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_on_findings and report["status"] != "complete":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
