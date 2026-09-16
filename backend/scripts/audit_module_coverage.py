"""Stage 14A: audit domain metric/tool/chapter coverage."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.urls import get_sync_engine
from app.models.metric_registry import MetricDefinition
from app.models.semantic_registry import ThresholdRule, ToolAlias, ToolDefinition
from app.services.semantic_tool_executors import semantic_executor_tool_ids
from app.services.module_contracts import build_compatibility_report
from app.services.tool_rag import load_tool_snapshot_sync


def _loads(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def _tool_id_for_metric(metric_key: str) -> str:
    return metric_key if metric_key.startswith("scenario_") else f"metric_{metric_key}"


def build_coverage_report(engine) -> dict[str, Any]:
    with Session(engine) as session:
        metrics = list(session.scalars(select(MetricDefinition).order_by(MetricDefinition.metric_key)))
        tools = list(session.scalars(select(ToolDefinition).order_by(ToolDefinition.tool_id)))
        aliases = list(session.scalars(select(ToolAlias)))
        thresholds = list(session.scalars(select(ThresholdRule)))

    tool_map = {tool.tool_id: tool for tool in tools}
    alias_map: dict[str, set[str]] = {}
    for alias in aliases:
        alias_map.setdefault(alias.tool_id, set()).add(alias.alias)
    threshold_map: dict[str, int] = Counter(
        rule.metric_key for rule in thresholds if rule.enabled and rule.status == "validated"
    )
    chapter_to_deps: dict[str, list[str]] = {}
    for tool in tools:
        if tool.kind == "chapter":
            chapter_to_deps[tool.tool_id] = [
                str(item) for item in _loads(tool.dependencies_json, [])
            ]

    executable_ids = semantic_executor_tool_ids()
    items: list[dict[str, Any]] = []
    for metric in metrics:
        tool_id = _tool_id_for_metric(metric.metric_key)
        tool = tool_map.get(tool_id)
        metric_aliases = set(_loads(metric.aliases_json, [])) | alias_map.get(tool_id, set())
        items.append(
            {
                "metric_key": metric.metric_key,
                "name": metric.name,
                "metric_type": metric.metric_type,
                "status": metric.status,
                "retrieval_enabled": metric.retrieval_enabled,
                "threshold_required": metric.threshold_required,
                "aliases": sorted(metric_aliases),
                "alias_count": len(metric_aliases),
                "tool_id": tool_id,
                "tool_status": tool.status if tool else None,
                "tool_enabled": tool.enabled if tool else False,
                "executor_registered": tool_id in executable_ids,
                "threshold_count": threshold_map.get(metric.metric_key, 0),
            }
        )

    validated_without_executor = [
        item["metric_key"]
        for item in items
        if item["status"] == "validated" and not item["executor_registered"]
    ]
    executable_without_alias = [
        item["metric_key"]
        for item in items
        if item["executor_registered"] and item["alias_count"] == 0
    ]
    thresholds_missing_required = [
        item["metric_key"]
        for item in items
        if item["threshold_required"] and item["threshold_count"] == 0
    ]
    chapter_gaps: list[dict[str, Any]] = []
    for chapter_id, dependencies in chapter_to_deps.items():
        missing = [tool_id for tool_id in dependencies if tool_id not in executable_ids]
        if missing:
            chapter_gaps.append({"chapter": chapter_id, "missing_executors": missing})

    summary = {
        "metrics_total": len(items),
        "metrics_validated": sum(1 for item in items if item["status"] == "validated"),
        "metrics_retrieval_enabled": sum(1 for item in items if item["retrieval_enabled"]),
        "metrics_executable": sum(1 for item in items if item["executor_registered"]),
        "metrics_with_aliases": sum(1 for item in items if item["alias_count"] > 0),
        "metrics_with_thresholds": sum(1 for item in items if item["threshold_count"] > 0),
        "tools_total": len(tools),
        "tools_validated": sum(1 for tool in tools if tool.status == "validated"),
        "tools_enabled": sum(1 for tool in tools if tool.enabled),
        "chapters_total": len(chapter_to_deps),
        "chapters_complete": len(chapter_to_deps) - len(chapter_gaps),
        "validated_without_executor": validated_without_executor,
        "executable_without_alias": executable_without_alias,
        "thresholds_missing_required": thresholds_missing_required,
        "chapter_gaps": chapter_gaps,
    }
    compatibility = build_compatibility_report(load_tool_snapshot_sync(engine))
    summary["composition"] = compatibility
    return {"summary": summary, "metrics": items}


def _print_human(report: dict[str, Any]) -> None:
    summary = report["summary"]
    for key, value in summary.items():
        if isinstance(value, list):
            print(f"{key}={len(value)}")
            for item in value[:20]:
                print(f"  - {item}")
        else:
            print(f"{key}={value}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = build_coverage_report(get_sync_engine())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    critical = bool(
        report["summary"]["validated_without_executor"]
        or report["summary"]["chapter_gaps"]
    )
    raise SystemExit(1 if args.strict and critical else 0)


if __name__ == "__main__":
    main()
