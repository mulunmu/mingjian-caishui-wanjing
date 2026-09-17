from __future__ import annotations

from sqlalchemy import create_engine, func, select
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
from app.services.semantic_registry_seed import seed_semantic_registry


def _engine():
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
    return engine


def test_seed_registry_marks_implemented_and_planned_tools_correctly():
    engine = _engine()
    result = seed_semantic_registry(engine)
    assert result["metrics"] >= 60
    assert result["tools"] >= result["metrics"]
    assert result["thresholds"] >= 5

    with Session(engine) as session:
        debt_metric = session.get(MetricDefinition, "debt_ratio")
        debt_tool = session.get(ToolDefinition, "metric_debt_ratio")
        loan_tool = session.get(ToolDefinition, "scenario_loan_readiness")
        assert debt_metric is not None and debt_metric.retrieval_enabled is True
        assert debt_tool is not None and debt_tool.status == "validated"
        assert debt_tool.enabled is True
        assert loan_tool is not None and loan_tool.status == "unsupported"
        assert loan_tool.enabled is False
        unsupported_metric = session.get(MetricDefinition, "scenario_loan_readiness")
        assert unsupported_metric is not None
        assert unsupported_metric.retrieval_enabled is False
        assert "不完整" in (unsupported_metric.edge_cases or "")
        cross_tool = session.get(ToolDefinition, "metric_cross_max_deviation")
        assert cross_tool is not None and cross_tool.status == "validated"


def test_seed_registry_adds_thresholds_aliases_and_chapters():
    engine = _engine()
    seed_semantic_registry(engine)
    with Session(engine) as session:
        assert session.get(ThresholdRule, "debt_ratio.default.gt.0.7.v1") is not None
        cross_rule = session.get(ThresholdRule, "cross_max_deviation.default.gte.0.4.v1")
        assert cross_rule is not None and cross_rule.status == "validated"
        assert session.get(ToolDefinition, "chapter_financial") is not None
        alias_count = session.scalar(
            select(func.count()).select_from(ToolAlias).where(
                ToolAlias.tool_id == "metric_debt_ratio"
            )
        )
        assert alias_count and alias_count > 0
        scenario_dependency = session.scalar(
            select(ToolDependency).where(
                ToolDependency.tool_id == "scenario_loan_readiness",
                ToolDependency.depends_on_tool_id == "metric_debt_ratio",
            )
        )
        assert scenario_dependency is not None
        english_alias = session.scalar(
            select(ToolAlias).where(
                ToolAlias.tool_id == "metric_debt_ratio",
                ToolAlias.alias == "debt ratio",
            )
        )
        assert english_alias is not None


def test_seed_registry_is_idempotent():
    engine = _engine()
    first = seed_semantic_registry(engine)
    with Session(engine) as session:
        first_aliases = session.scalar(select(func.count()).select_from(ToolAlias))
        first_dependencies = session.scalar(select(func.count()).select_from(ToolDependency))

    second = seed_semantic_registry(engine)
    with Session(engine) as session:
        second_aliases = session.scalar(select(func.count()).select_from(ToolAlias))
        second_dependencies = session.scalar(select(func.count()).select_from(ToolDependency))

    assert first == second
    assert first_aliases == second_aliases
    assert first_dependencies == second_dependencies
