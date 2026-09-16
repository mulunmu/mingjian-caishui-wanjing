"""Readiness checks for persisted composition execution evidence."""
from __future__ import annotations

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models.composition_blueprint import CompositionBlueprintRecord
from app.models.composition_checkpoint import CompositionExecutionCheckpoint
from app.models.composition_migration import CompositionMigrationApproval


def build_composition_readiness_report(engine) -> dict:
    tables = set(inspect(engine).get_table_names())
    required = {
        "composition_blueprint",
        "composition_execution_checkpoint",
        "composition_migration_approval",
    }
    missing = sorted(required - tables)
    counts = {
        "blueprints": 0,
        "checkpoints": 0,
        "completed_checkpoints": 0,
        "migration_approvals": 0,
    }
    if not missing:
        with Session(engine) as session:
            counts["blueprints"] = int(
                session.scalar(select(func.count()).select_from(CompositionBlueprintRecord)) or 0
            )
            counts["checkpoints"] = int(
                session.scalar(select(func.count()).select_from(CompositionExecutionCheckpoint)) or 0
            )
            counts["completed_checkpoints"] = int(
                session.scalar(
                    select(func.count())
                    .select_from(CompositionExecutionCheckpoint)
                    .where(CompositionExecutionCheckpoint.status == "completed")
                )
                or 0
            )
            counts["migration_approvals"] = int(
                session.scalar(select(func.count()).select_from(CompositionMigrationApproval)) or 0
            )
    failures = []
    if missing:
        failures.append("missing_tables:" + ",".join(missing))
    if not missing and counts["blueprints"] <= 0:
        failures.append("no_persisted_blueprints")
    if not missing and counts["completed_checkpoints"] <= 0:
        failures.append("no_completed_checkpoints")
    return {"ok": not failures, "failures": failures, "counts": counts}
