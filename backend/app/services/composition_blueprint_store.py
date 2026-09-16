"""Persist, version, load, and replay composition plans."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.composition_blueprint import CompositionBlueprintRecord
from app.models.composition_migration import CompositionMigrationApproval
from app.schemas.composition import CompositionPlan
from app.services.composition_validator import validate_composition_plan


class CompositionBlueprintVersionError(ValueError):
    pass


def save_composition_blueprint(
    session: Session,
    plan: CompositionPlan,
    *,
    registry_version: str,
    owner: str | None = None,
    session_id: str | None = None,
    objective: str = "",
    status: str = "active",
) -> CompositionBlueprintRecord:
    record = session.get(CompositionBlueprintRecord, plan.plan_id)
    now = datetime.now(timezone.utc)
    if record is None:
        record = CompositionBlueprintRecord(
            plan_id=plan.plan_id,
            created_at=now,
            version=0,
        )
        session.add(record)
    record.owner = owner
    record.session_id = session_id
    record.registry_version = registry_version
    plan_json = json.dumps(plan.model_dump(mode="json"), ensure_ascii=False)
    if record.version and record.registry_version == registry_version and record.plan_json == plan_json:
        return record
    record.plan_json = plan_json
    record.objective = objective
    record.version = int(record.version or 0) + 1
    record.status = status
    record.updated_at = now
    session.flush()
    return record


def load_composition_blueprint(
    session: Session,
    plan_id: str,
    *,
    registry_version: str | None = None,
) -> CompositionPlan | None:
    record = session.get(CompositionBlueprintRecord, plan_id)
    if record is None or record.status != "active":
        return None
    if registry_version is not None and record.registry_version != registry_version:
        raise CompositionBlueprintVersionError(
            f"registry version mismatch: {record.registry_version} != {registry_version}"
        )
    return CompositionPlan.model_validate(json.loads(record.plan_json or "{}"))


def snapshot_registry_version(snapshot) -> str:
    payload = "|".join(
        f"{tool.tool_id}:{tool.title}:{tool.kind}" for tool in snapshot.tools
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def save_composition_blueprint_sync(
    engine,
    plan: CompositionPlan,
    *,
    registry_version: str,
    owner: str | None = None,
    session_id: str | None = None,
) -> None:
    with Session(engine) as session:
        save_composition_blueprint(
            session,
            plan,
            registry_version=registry_version,
            owner=owner,
            session_id=session_id,
        )
        session.commit()


def replay_composition_blueprint_sync(
    engine,
    plan_id: str,
    *,
    registry_version: str,
    modules,
) -> CompositionPlan:
    with Session(engine) as session:
        return replay_composition_blueprint(
            session,
            plan_id,
            registry_version=registry_version,
            modules=modules,
        )


def load_or_migrate_composition_blueprint(
    session: Session,
    plan_id: str,
    *,
    registry_version: str,
    modules,
) -> CompositionPlan:
    record = session.get(CompositionBlueprintRecord, plan_id)
    if record is None or record.status != "active":
        raise CompositionBlueprintVersionError(f"active blueprint not found: {plan_id}")
    plan = CompositionPlan.model_validate(json.loads(record.plan_json or "{}"))
    if record.registry_version != registry_version:
        approval = (
            session.query(CompositionMigrationApproval)
            .filter(
                CompositionMigrationApproval.plan_id == plan_id,
                CompositionMigrationApproval.from_version == record.registry_version,
                CompositionMigrationApproval.to_version == registry_version,
                CompositionMigrationApproval.status == "approved",
            )
            .first()
        )
        if approval is None:
            raise CompositionBlueprintVersionError(
                f"registry migration approval required: {record.registry_version} -> {registry_version}"
            )
    report = validate_composition_plan(plan, modules)
    if not report.valid:
        raise CompositionBlueprintVersionError(
            "blueprint cannot migrate: "
            + ", ".join(error.code for error in report.errors)
        )
    now = datetime.now(timezone.utc)
    record.registry_version = registry_version
    record.version = int(record.version or 0) + 1
    record.updated_at = now
    session.flush()
    return plan


def approve_composition_migration(
    session: Session,
    *,
    plan_id: str,
    from_version: str,
    to_version: str,
    approved_by: str,
    note: str = "",
) -> CompositionMigrationApproval:
    existing = (
        session.query(CompositionMigrationApproval)
        .filter(
            CompositionMigrationApproval.plan_id == plan_id,
            CompositionMigrationApproval.from_version == from_version,
            CompositionMigrationApproval.to_version == to_version,
            CompositionMigrationApproval.status == "approved",
        )
        .first()
    )
    if existing is not None:
        return existing
    approval = CompositionMigrationApproval(
        plan_id=plan_id,
        from_version=from_version,
        to_version=to_version,
        approved_by=approved_by,
        note=note,
        created_at=datetime.now(timezone.utc),
    )
    session.add(approval)
    session.flush()
    return approval


def replay_composition_blueprint(
    session: Session,
    plan_id: str,
    *,
    registry_version: str,
    modules,
) -> CompositionPlan:
    plan = load_composition_blueprint(
        session,
        plan_id,
        registry_version=registry_version,
    )
    if plan is None:
        raise CompositionBlueprintVersionError(f"active blueprint not found: {plan_id}")
    report = validate_composition_plan(plan, modules)
    if not report.valid:
        raise CompositionBlueprintVersionError(
            "blueprint no longer validates: "
            + ", ".join(error.code for error in report.errors)
        )
    return plan
