from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.composition_blueprint import CompositionBlueprintRecord
from app.schemas.composition import CompositionNode, CompositionPlan
from app.services.composition_blueprint_store import (
    CompositionBlueprintVersionError,
    load_composition_blueprint,
    save_composition_blueprint,
    replay_composition_blueprint,
)
from tests.test_composition_planner import _modules


def _engine():
    from tests.test_semantic_registry_seed import _engine as registry_engine

    engine = registry_engine()
    Base.metadata.create_all(engine, tables=[CompositionBlueprintRecord.__table__])
    return engine


def _plan() -> CompositionPlan:
    return CompositionPlan(
        plan_id="plan-persist-1",
        nodes=[
            CompositionNode(node_id="a", module_id="metric_debt_ratio"),
            CompositionNode(node_id="b", module_id="metric_cash_flow_net"),
        ],
        output_node_ids=["a", "b"],
    )


def test_blueprint_save_load_roundtrip():
    engine = _engine()
    with Session(engine) as session:
        record = save_composition_blueprint(
            session,
            _plan(),
            registry_version="registry-v1",
            owner="u@example.com",
            session_id="s1",
        )
        session.commit()
        assert record.version == 1

    with Session(engine) as session:
        loaded = load_composition_blueprint(
            session,
            "plan-persist-1",
            registry_version="registry-v1",
        )
    assert loaded == _plan()


def test_blueprint_registry_version_mismatch_rejected():
    engine = _engine()
    with Session(engine) as session:
        save_composition_blueprint(
            session,
            _plan(),
            registry_version="registry-v1",
        )
        session.commit()
        with pytest.raises(CompositionBlueprintVersionError):
            load_composition_blueprint(
                session,
                "plan-persist-1",
                registry_version="registry-v2",
            )


def test_replay_validates_loaded_plan():
    engine = _engine()
    with Session(engine) as session:
        save_composition_blueprint(
            session,
            _plan(),
            registry_version="registry-v1",
        )
        session.commit()
        replayed = replay_composition_blueprint(
            session,
            "plan-persist-1",
            registry_version="registry-v1",
            modules=_modules(),
        )
    assert replayed == _plan()
