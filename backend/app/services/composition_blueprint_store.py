"""Persist, version, load, and replay composition plans."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.composition_blueprint import CompositionBlueprintRecord
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
