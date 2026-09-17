from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.report_blueprint import ReportBlueprintRecord
from app.models.shadow_answer_evaluation import ShadowAnswerObservationRecord
from app.models.shadow_evaluation import ShadowEvaluationRecord
from app.models.semantic_registry import ToolDefinition
from app.services.deployment_readiness import build_semantic_readiness_report
from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.shadow_reporting import build_shadow_evaluation_summary
from tests.test_semantic_registry_seed import _engine


def _deployment_engine():
    engine = _engine()
    Base.metadata.create_all(
        engine,
        tables=[
            ReportBlueprintRecord.__table__,
            ShadowEvaluationRecord.__table__,
            ShadowAnswerObservationRecord.__table__,
        ],
    )
    seed_semantic_registry(engine)
    return engine


def test_semantic_readiness_passes_after_seed():
    report = build_semantic_readiness_report(_deployment_engine())
    assert report["ok"] is True
    assert report["missing_tables"] == []
    assert report["counts"]["validated_metrics"] >= 50
    assert report["counts"]["validated_tools"] >= 60


def test_semantic_readiness_rejects_enabled_planned_tool():
    engine = _deployment_engine()
    with Session(engine) as session:
        tool = session.get(ToolDefinition, "scenario_loan_readiness")
        assert tool is not None
        tool.enabled = True
        session.commit()
    report = build_semantic_readiness_report(engine)
    assert report["ok"] is False
    assert any(item.startswith("unsupported_tools_enabled") for item in report["failures"])


def test_semantic_readiness_rejects_missing_topic_memory_columns():
    engine = _deployment_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE conversation_topic"))
        conn.execute(text("CREATE TABLE conversation_topic (topic_id VARCHAR(64))"))
    report = build_semantic_readiness_report(engine)
    assert report["ok"] is False
    assert report["missing_conversation_topic_columns"] == [
        "claim_ids_json",
        "report_ids_json",
        "tool_plan_json",
    ]


def test_shadow_report_requires_samples():
    report = build_shadow_evaluation_summary(_deployment_engine(), min_samples=1)
    assert report["ok"] is False
    assert "no_shadow_samples" in report["failures"]


def test_shadow_report_passes_when_thresholds_met():
    engine = _deployment_engine()
    with Session(engine) as session:
        for index in range(20):
            session.add(
                ShadowEvaluationRecord(
                    query_digest=f"digest-{index}",
                    session_id="shadow-session",
                    legacy_route="analysis",
                    shadow_route="analysis",
                    legacy_domain="warn",
                    shadow_domain="warn",
                    route_match=True,
                    domain_match=True,
                    tool_coverage=1.0,
                    legacy_latency_ms=100.0,
                    shadow_latency_ms=120.0,
                    switch_eligible=True,
                    mismatch_reasons_json="[]",
                )
            )
        session.commit()
    report = build_shadow_evaluation_summary(engine, min_samples=20)
    assert report["ok"] is True
    assert report["samples"] == 20
    assert report["switch_eligible_rate"] == 1.0
