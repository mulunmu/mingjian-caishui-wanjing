from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.composition_blueprint import CompositionBlueprintRecord
from app.models.composition_migration import CompositionMigrationApproval
from app.services.composition_blueprint_store import (
    CompositionBlueprintVersionError,
    approve_composition_migration,
    load_or_migrate_composition_blueprint,
    save_composition_blueprint,
)
from tests.test_composition_blueprint_store import _plan
from tests.test_composition_planner import _modules


def _engine():
    from tests.test_semantic_registry_seed import _engine as registry_engine

    engine = registry_engine()
    Base.metadata.create_all(
        engine,
        tables=[
            CompositionBlueprintRecord.__table__,
            CompositionMigrationApproval.__table__,
        ],
    )
    return engine


def test_migration_requires_explicit_approval():
    engine = _engine()
    with Session(engine) as session:
        save_composition_blueprint(session, _plan(), registry_version="v1")
        session.commit()
        try:
            load_or_migrate_composition_blueprint(
                session,
                "plan-persist-1",
                registry_version="v2",
                modules=_modules(),
            )
        except CompositionBlueprintVersionError as exc:
            assert "approval" in str(exc)
        else:
            raise AssertionError("migration should require approval")


def test_approved_migration_updates_registry_version_and_plan_version():
    engine = _engine()
    with Session(engine) as session:
        save_composition_blueprint(session, _plan(), registry_version="v1")
        approve_composition_migration(
            session,
            plan_id="plan-persist-1",
            from_version="v1",
            to_version="v2",
            approved_by="admin@example.com",
        )
        session.commit()
        migrated = load_or_migrate_composition_blueprint(
            session,
            "plan-persist-1",
            registry_version="v2",
            modules=_modules(),
        )
        assert migrated == _plan()
        record = session.get(CompositionBlueprintRecord, "plan-persist-1")
        assert record.registry_version == "v2"
        assert record.version == 2
