from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.composition_blueprint import CompositionBlueprintRecord
from app.models.composition_checkpoint import CompositionExecutionCheckpoint
from app.models.composition_migration import CompositionMigrationApproval
from app.services.composition_readiness import build_composition_readiness_report


def test_composition_readiness_passes_with_persisted_evidence():
    from tests.test_semantic_registry_seed import _engine as registry_engine

    engine = registry_engine()
    Base.metadata.create_all(
        engine,
        tables=[
            CompositionBlueprintRecord.__table__,
            CompositionExecutionCheckpoint.__table__,
            CompositionMigrationApproval.__table__,
        ],
    )
    with Session(engine) as session:
        session.add(
            CompositionBlueprintRecord(
                plan_id="plan-1",
                registry_version="v1",
                plan_json="{}",
                version=1,
                status="active",
            )
        )
        session.add(
            CompositionExecutionCheckpoint(
                execution_id="exec-1",
                plan_id="plan-1",
                registry_version="v1",
                status="completed",
                state_json="{}",
            )
        )
        session.commit()

    report = build_composition_readiness_report(engine)
    assert report["ok"] is True
    assert report["counts"]["blueprints"] == 1
    assert report["counts"]["completed_checkpoints"] == 1
