"""Execute a report plan by binding collected chapter claims to blocks."""
from __future__ import annotations

from typing import Any

from app.schemas.report_plan import ReportPlan
from app.services.report_planner import bind_report_plan_claims
from app.services.report_plan_validator import validate_report_plan


def execute_report_plan(
    plan: ReportPlan,
    chapters: list[dict[str, Any]],
) -> dict[str, Any]:
    bound = bind_report_plan_claims(plan, chapters)
    report = validate_report_plan(bound)
    return {
        "report_plan": bound.model_dump(mode="json"),
        "validation": report.model_dump(mode="json"),
        "chapters": chapters,
    }
