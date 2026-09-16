from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.metric_registry import MetricDefinition
from app.models.semantic_registry import (
    ConversationTopic,
    ThresholdRule,
    ToolAlias,
    ToolDefinition,
    ToolDependency,
    ToolExample,
)


def test_semantic_registry_tables_can_be_created_and_queried():
    engine = create_engine("sqlite:///:memory:")
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
        ],
    )
    with Session(engine) as session:
        tool = ToolDefinition(
            tool_id="metric_debt_ratio",
            kind="atomic_metric",
            title="资产负债率",
            description="负债总额/资产总额",
            input_schema_json='{"type":"object"}',
            output_schema_json='{"type":"object"}',
            required_params_json='["entity"]',
            dependencies_json="[]",
            chapter_links_json='["chapter_financial"]',
            scenarios_json='["loan","warn"]',
            shape="single_value",
            version=1,
            status="validated",
            enabled=True,
        )
        session.add(tool)
        session.add(
            ThresholdRule(
                rule_id="debt_ratio.default.gt.0.7.v1",
                metric_key="debt_ratio",
                scope_json="{}",
                operator="gt",
                threshold_json='{"value":0.7}',
                severity="warn",
                action="核查偿债能力",
                source="baseline",
                version=1,
                status="validated",
                enabled=True,
            )
        )
        session.add(
            ToolAlias(
                tool_id=tool.tool_id,
                alias="负债高不高",
                alias_type="query",
                language="zh",
                weight=100,
            )
        )
        session.add(
            ToolDependency(
                tool_id="chapter_financial",
                depends_on_tool_id=tool.tool_id,
                relation="requires",
            )
        )
        session.add(
            ToolExample(
                tool_id=tool.tool_id,
                query_text="这家企业负债压力大不大",
                example_type="positive",
                language="zh",
                metadata_json="{}",
            )
        )
        session.add(
            ConversationTopic(
                topic_id="topic-1",
                session_id="session-1",
                turn_index=1,
                summary="资产负债率查询",
                entities_json='["企业17"]',
                filters_json="{}",
                scenario="loan",
                intent="lookup",
                tool_plan_json="[]",
                claim_ids_json="[]",
                status="active",
            )
        )
        session.commit()

        assert session.scalar(
            select(ToolDefinition).where(ToolDefinition.tool_id == "metric_debt_ratio")
        ) is not None
        assert session.scalar(
            select(ThresholdRule).where(ThresholdRule.metric_key == "debt_ratio")
        ) is not None


def test_metric_definition_has_v2_retrieval_metadata():
    columns = set(MetricDefinition.__table__.columns.keys())
    assert {
        "category",
        "version",
        "status",
        "shape",
        "retrieval_enabled",
        "aliases_json",
        "source_tables_json",
    } <= columns
