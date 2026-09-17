from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.report_blueprint import ReportBlueprintRecord
from app.models.shadow_answer_evaluation import ShadowAnswerObservationRecord
from app.models.shadow_evaluation import ShadowEvaluationRecord
from app.models.semantic_registry import ToolDefinition
from app.services.deployment_gate import build_deployment_gate
from app.services.semantic_registry_seed import seed_semantic_registry
from tests.test_semantic_registry_seed import _engine


def _gate_engine():
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


def _add_shadow_samples(engine, count: int = 20) -> None:
    with Session(engine) as session:
        for index in range(count):
            session.add(
                ShadowEvaluationRecord(
                    query_digest=f"gate-{index}",
                    session_id="gate-session",
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


def _add_answer_samples(engine, count: int = 20) -> None:
    with Session(engine) as session:
        for index in range(count):
            session.add(
                ShadowAnswerObservationRecord(
                    query_digest=f"answer-{index}",
                    session_id="gate-session",
                    status="answered",
                    route="analysis",
                    domain="warn",
                    candidate_tool_ids_json='["metric_debt_ratio"]',
                    plan_tool_ids_json='["metric_debt_ratio"]',
                    claim_count=1,
                    reply_present=True,
                    latency_ms=140.0,
                    error=None,
                )
            )
        session.commit()


def test_gate_stays_on_legacy_without_shadow_samples():
    report = build_deployment_gate(_gate_engine(), min_shadow_samples=20)
    assert report["ok"] is False
    assert report["decision"] == "stay_on_legacy"
    assert any(item.startswith("shadow:") for item in report["blockers"])
    assert any(item.startswith("answer:") for item in report["blockers"])


def test_gate_is_ready_for_canary_when_all_checks_pass():
    engine = _gate_engine()
    _add_shadow_samples(engine)
    _add_answer_samples(engine)
    report = build_deployment_gate(engine, min_shadow_samples=20)
    assert report["ok"] is True
    assert report["decision"] == "ready_for_canary"
    assert report["blockers"] == []


def test_gate_blocks_when_planned_tool_is_enabled():
    engine = _gate_engine()
    _add_shadow_samples(engine)
    _add_answer_samples(engine)
    with Session(engine) as session:
        tool = session.get(ToolDefinition, "scenario_loan_readiness")
        assert tool is not None
        tool.enabled = True
        session.commit()
    report = build_deployment_gate(engine, min_shadow_samples=20)
    assert report["ok"] is False
    assert any("unsupported_tools_enabled" in item for item in report["blockers"])
