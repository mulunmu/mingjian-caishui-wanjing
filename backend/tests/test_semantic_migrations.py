from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.db.session import Base
from app.db.semantic_migrations import ensure_metric_definition_v2_columns
from app.models.metric_registry import MetricDefinition
from app.models.semantic_registry import (
    ConversationTopic,
    ThresholdRule,
    ToolAlias,
    ToolDefinition,
    ToolDependency,
    ToolExample,
)
from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.topic_memory import append_topic, rollback_topic
from app.schemas.tool_plan import ToolPlan, ToolStep
from app.services.plan_execution import execute_tool_plan
from app.services.tool_rag import load_tool_snapshot_sync
from app.models.report_blueprint import ReportBlueprintRecord
from app.models.shadow_evaluation import ShadowEvaluationRecord
from app.schemas.report_blueprint import BlockPlan, ReportBlueprint, ReportScope, SectionPlan
from app.services.report_blueprint import (compile_report_blueprint, execute_report_blueprint, load_report_blueprint, save_report_blueprint)
from app.services.shadow_integration import run_shadow_evaluation_sync


@pytest.mark.skipif(
    not os.getenv("SEMANTIC_TEST_DATABASE_URL"),
    reason="SEMANTIC_TEST_DATABASE_URL not configured",
)
def test_metric_definition_v2_migration_is_idempotent():
    engine = create_engine(os.environ["SEMANTIC_TEST_DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS metric_definition"))
        conn.execute(
            text(
                "CREATE TABLE metric_definition ("
                "metric_key VARCHAR(64) PRIMARY KEY, "
                "name VARCHAR(120) NOT NULL, "
                "description TEXT NOT NULL, "
                "metric_type VARCHAR(20) NOT NULL DEFAULT 'computed', "
                "formula TEXT, "
                "unit VARCHAR(20) NOT NULL DEFAULT '', "
                "grain VARCHAR(30) NOT NULL DEFAULT 'enterprise', "
                "source_fields_json TEXT NOT NULL DEFAULT '[]', "
                "dimensions_json TEXT NOT NULL DEFAULT '[]', "
                "default_filters_json TEXT NOT NULL DEFAULT '{}', "
                "edge_cases TEXT, "
                "is_canonical BOOLEAN NOT NULL DEFAULT FALSE, "
                "updated_at TIMESTAMP"
                ")"
            )
        )

    ensure_metric_definition_v2_columns(engine)
    ensure_metric_definition_v2_columns(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("metric_definition")}
    assert {
        "category",
        "version",
        "status",
        "shape",
        "retrieval_enabled",
        "aliases_json",
        "source_tables_json",
    } <= columns


@pytest.mark.skipif(
    not os.getenv("SEMANTIC_TEST_DATABASE_URL"),
    reason="SEMANTIC_TEST_DATABASE_URL not configured",
)
def test_registry_tables_create_on_postgresql():
    engine = create_engine(os.environ["SEMANTIC_TEST_DATABASE_URL"])
    tables = [
        MetricDefinition.__table__,
        ThresholdRule.__table__,
        ToolDefinition.__table__,
        ToolAlias.__table__,
        ToolDependency.__table__,
        ToolExample.__table__,
        ConversationTopic.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    names = set(inspect(engine).get_table_names())
    assert {
        "metric_definition",
        "threshold_rule",
        "tool_definition",
        "tool_alias",
        "tool_dependency",
        "tool_example",
        "conversation_topic",
    } <= names


@pytest.mark.skipif(
    not os.getenv("SEMANTIC_TEST_DATABASE_URL"),
    reason="SEMANTIC_TEST_DATABASE_URL not configured",
)
def test_registry_seed_is_idempotent_on_postgresql():
    engine = create_engine(os.environ["SEMANTIC_TEST_DATABASE_URL"])
    ensure_metric_definition_v2_columns(engine)
    tables = [
        MetricDefinition.__table__,
        ThresholdRule.__table__,
        ToolDefinition.__table__,
        ToolAlias.__table__,
        ToolDependency.__table__,
        ToolExample.__table__,
        ConversationTopic.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)

    first = seed_semantic_registry(engine)
    second = seed_semantic_registry(engine)
    assert first == second
    assert first["metrics"] >= 60
    assert first["tools"] >= first["metrics"]


@pytest.mark.skipif(
    not os.getenv("SEMANTIC_TEST_DATABASE_URL"),
    reason="SEMANTIC_TEST_DATABASE_URL not configured",
)
def test_topic_memory_rollback_on_postgresql():
    engine = create_engine(os.environ["SEMANTIC_TEST_DATABASE_URL"])
    Base.metadata.create_all(engine, tables=[ConversationTopic.__table__])
    session_id = "postgres-topic-memory"
    with Session(engine) as session:
        session.query(ConversationTopic).filter(
            ConversationTopic.session_id == session_id
        ).delete()
        append_topic(
            session,
            session_id=session_id,
            summary="制造业风险",
            entities=["ENT017"],
            filters={"industry_l1": "制造业"},
            scenario="warn",
            intent="fraud",
        )
        append_topic(
            session,
            session_id=session_id,
            summary="天气",
            entities=[],
            filters={},
            scenario=None,
            intent="out_of_domain",
        )
        target = rollback_topic(session, session_id, "回到上一个问题")
        target_summary = target.summary
        session.commit()
    with Session(engine) as session:
        rows = list(
            session.query(ConversationTopic)
            .filter(ConversationTopic.session_id == session_id)
            .order_by(ConversationTopic.turn_index)
        )
    assert target_summary == "天气"
    assert [row.status for row in rows] == ["completed", "active"]


@pytest.mark.skipif(
    not os.getenv("SEMANTIC_TEST_DATABASE_URL"),
    reason="SEMANTIC_TEST_DATABASE_URL not configured",
)
def test_plan_execution_on_postgresql():
    engine = create_engine(os.environ["SEMANTIC_TEST_DATABASE_URL"])
    ensure_metric_definition_v2_columns(engine)
    tables = [
        MetricDefinition.__table__,
        ThresholdRule.__table__,
        ToolDefinition.__table__,
        ToolAlias.__table__,
        ToolDependency.__table__,
        ToolExample.__table__,
        ConversationTopic.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    seed_semantic_registry(engine)
    snapshot = load_tool_snapshot_sync(engine)
    plan = ToolPlan(
        mode="answer",
        steps=[
            ToolStep(
                step_id="debt",
                tool_id="metric_debt_ratio",
                params={"entity": "ENT017"},
            )
        ],
    )
    execution = execute_tool_plan(
        plan,
        snapshot,
        {
            "metric_debt_ratio": lambda **_: {
                "metric": "debt_ratio",
                "value": 0.72,
            }
        },
    )
    assert execution.claims == [{"metric": "debt_ratio", "value": 0.72}]


@pytest.mark.skipif(
    not os.getenv("SEMANTIC_TEST_DATABASE_URL"),
    reason="SEMANTIC_TEST_DATABASE_URL not configured",
)
def test_report_blueprint_persistence_on_postgresql():
    engine = create_engine(os.environ["SEMANTIC_TEST_DATABASE_URL"])
    ensure_metric_definition_v2_columns(engine)
    Base.metadata.create_all(
        engine,
        tables=[
            MetricDefinition.__table__,
            ThresholdRule.__table__,
            ToolDefinition.__table__,
            ToolAlias.__table__,
            ToolDependency.__table__,
            ToolExample.__table__,
            ConversationTopic.__table__,
            ReportBlueprintRecord.__table__,
        ],
    )
    seed_semantic_registry(engine)
    snapshot = load_tool_snapshot_sync(engine)
    blueprint = ReportBlueprint(
        objective="PostgreSQL blueprint",
        scope=ReportScope(sample_mode="entities", entity_ids=["ENT017"]),
        sections=[
            SectionPlan(
                section_id="financial",
                chapter_key="financial",
                steps=[
                    ToolStep(
                        step_id="debt",
                        tool_id="metric_debt_ratio",
                        params={"entity": "ENT017"},
                    )
                ],
                blocks=[
                    BlockPlan(
                        block_id="debt-kpi",
                        kind="kpi",
                        source_tool_id="metric_debt_ratio",
                    )
                ],
            )
        ],
    )
    with Session(engine) as session:
        record = save_report_blueprint(
            session,
            blueprint,
            owner="postgres@example.com",
            session_id="postgres-session",
        )
        session.commit()
        blueprint_id = record.blueprint_id
    with Session(engine) as session:
        loaded = load_report_blueprint(session, blueprint_id)
    assert loaded is not None
    compiled = compile_report_blueprint(loaded, snapshot)
    execution = execute_report_blueprint(
        compiled,
        snapshot,
        {
            "metric_debt_ratio": lambda **_: {
                "metric": "debt_ratio",
                "value": 0.72,
            }
        },
    )
    assert execution.blueprint_id == blueprint_id
    assert execution.sections["financial"].claims == [
        {"metric": "debt_ratio", "value": 0.72}
    ]

@pytest.mark.skipif(
    not os.getenv("SEMANTIC_TEST_DATABASE_URL"),
    reason="SEMANTIC_TEST_DATABASE_URL not configured",
)
def test_shadow_evaluation_persists_on_postgresql():
    engine = create_engine(os.environ["SEMANTIC_TEST_DATABASE_URL"])
    Base.metadata.create_all(engine, tables=[ShadowEvaluationRecord.__table__])
    seed_semantic_registry(engine)
    comparison = run_shadow_evaluation_sync(
        engine,
        "企业17增值税税负高不高",
        {
            "reply": "ok",
            "function": "tax",
            "query_type": "aggregation",
            "data": {"dialog_act": {"act": "analyze", "scenario": "warn"}},
        },
        session_id="postgres-shadow",
        legacy_latency_ms=50.0,
    )
    assert comparison.legacy_route == "analysis"
    assert comparison.shadow_route == "analysis"
    with Session(engine) as session:
        count = session.query(ShadowEvaluationRecord).filter(
            ShadowEvaluationRecord.session_id == "postgres-shadow"
        ).count()
    assert count == 1