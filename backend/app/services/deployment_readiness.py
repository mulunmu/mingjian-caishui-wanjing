"""Readiness checks for semantic RAG and shadow deployment."""
from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session

from app.models.metric_registry import MetricDefinition
from app.models.semantic_registry import ThresholdRule, ToolDefinition


REQUIRED_TABLES = {
    "metric_definition",
    "threshold_rule",
    "tool_definition",
    "tool_alias",
    "tool_dependency",
    "tool_example",
    "conversation_topic",
    "report_blueprint",
    "shadow_evaluation",
    "shadow_answer_observation",
}

REQUIRED_CONVERSATION_TOPIC_COLUMNS = {
    "tool_plan_json",
    "claim_ids_json",
    "report_ids_json",
}


def _status_counts(session: Session, model) -> dict[str, int]:
    rows = session.execute(
        select(model.status, func.count()).group_by(model.status)
    ).all()
    return {str(status): int(count) for status, count in rows}


def build_semantic_readiness_report(
    engine: Engine,
    *,
    min_validated_metrics: int = 50,
    min_validated_tools: int = 60,
    min_validated_thresholds: int = 14,
) -> dict:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - tables)
    topic_columns = (
        {column["name"] for column in inspector.get_columns("conversation_topic")}
        if "conversation_topic" in tables
        else set()
    )
    missing_topic_columns = sorted(
        REQUIRED_CONVERSATION_TOPIC_COLUMNS - topic_columns
    )

    metric_status: dict[str, int] = {}
    tool_status: dict[str, int] = {}
    threshold_status: dict[str, int] = {}
    planned_enabled_tools: list[str] = []
    unsupported_enabled_tools: list[str] = []
    if not missing_tables:
        with Session(engine) as session:
            metric_status = _status_counts(session, MetricDefinition)
            tool_status = _status_counts(session, ToolDefinition)
            threshold_status = _status_counts(session, ThresholdRule)
            planned_enabled_tools = list(
                session.scalars(
                    select(ToolDefinition.tool_id).where(
                        ToolDefinition.status == "planned",
                        ToolDefinition.enabled.is_(True),
                    )
                )
            )
            unsupported_enabled_tools = list(
                session.scalars(
                    select(ToolDefinition.tool_id).where(
                        ToolDefinition.status == "unsupported",
                        ToolDefinition.enabled.is_(True),
                    )
                )
            )

    failures: list[str] = []
    if missing_tables:
        failures.append(f"missing_tables:{missing_tables}")
    if missing_topic_columns:
        failures.append(
            f"missing_conversation_topic_columns:{missing_topic_columns}"
        )
    if metric_status.get("validated", 0) < min_validated_metrics:
        failures.append(
            f"validated_metrics_below_min:{metric_status.get('validated', 0)}"
        )
    if tool_status.get("validated", 0) < min_validated_tools:
        failures.append(
            f"validated_tools_below_min:{tool_status.get('validated', 0)}"
        )
    if threshold_status.get("validated", 0) < min_validated_thresholds:
        failures.append(
            f"validated_thresholds_below_min:{threshold_status.get('validated', 0)}"
        )
    if planned_enabled_tools:
        failures.append(f"planned_tools_enabled:{planned_enabled_tools}")
    if unsupported_enabled_tools:
        failures.append(f"unsupported_tools_enabled:{unsupported_enabled_tools}")

    return {
        "ok": not failures,
        "missing_tables": missing_tables,
        "missing_conversation_topic_columns": missing_topic_columns,
        "metric_status": metric_status,
        "tool_status": tool_status,
        "threshold_status": threshold_status,
        "planned_enabled_tools": planned_enabled_tools,
        "unsupported_enabled_tools": unsupported_enabled_tools,
        "counts": {
            "tables": len(REQUIRED_TABLES),
            "validated_metrics": metric_status.get("validated", 0),
            "validated_tools": tool_status.get("validated", 0),
            "validated_thresholds": threshold_status.get("validated", 0),
        },
        "failures": failures,
    }
