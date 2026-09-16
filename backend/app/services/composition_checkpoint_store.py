"""Persist and restore composition execution checkpoints."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.composition_checkpoint import CompositionExecutionCheckpoint


def save_checkpoint_sync(
    engine,
    *,
    execution_id: str,
    plan_id: str,
    registry_version: str,
    state: dict,
    status: str = "running",
) -> None:
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        record = session.get(CompositionExecutionCheckpoint, execution_id)
        if record is None:
            record = CompositionExecutionCheckpoint(
                execution_id=execution_id,
                created_at=now,
            )
            session.add(record)
        record.plan_id = plan_id
        record.registry_version = registry_version
        record.status = status
        record.state_json = json.dumps(state, ensure_ascii=False, default=str)
        record.updated_at = now
        session.commit()


def load_checkpoint_sync(engine, execution_id: str) -> dict | None:
    with Session(engine) as session:
        record = session.get(CompositionExecutionCheckpoint, execution_id)
        if record is None:
            return None
        return json.loads(record.state_json or "{}")
