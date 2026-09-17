from __future__ import annotations

from copy import deepcopy

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.shadow_evaluation import ShadowEvaluationRecord
from app.schemas.conversation_route import ConversationPolicy
from app.schemas.shadow_evaluation import LegacyDialogueSnapshot
from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.shadow_integration import (
    compare_snapshots,
    dialog_act_to_raw_route,
    legacy_snapshot_from_result,
    run_shadow_evaluation_sync,
)
from tests.test_semantic_registry_seed import _engine


def _engine_with_shadow():
    engine = _engine()
    Base.metadata.create_all(engine, tables=[ShadowEvaluationRecord.__table__])
    seed_semantic_registry(engine)
    return engine


def test_legacy_greeting_maps_to_shadow_greeting_without_tools():
    engine = _engine_with_shadow()
    result = {
        "reply": "你好",
        "parse_source": "meta_greeting",
        "function": "general",
        "data": {"dialog_act": {"act": "meta_session"}},
    }
    comparison = run_shadow_evaluation_sync(
        engine,
        "你好",
        result,
        legacy_latency_ms=20.0,
    )
    assert comparison.legacy_route == "greeting"
    assert comparison.shadow_route == "greeting"
    assert comparison.candidate_tool_ids == []
    assert comparison.switch_eligible is True


def test_validated_tax_query_matches_and_persists_shadow_record():
    engine = _engine_with_shadow()
    result = {
        "reply": "ok",
        "function": "tax",
        "query_type": "aggregation",
        "data": {"dialog_act": {"act": "analyze", "scenario": "warn"}},
    }
    comparison = run_shadow_evaluation_sync(
        engine,
        "企业17增值税税负高不高",
        result,
        session_id="session-shadow",
        legacy_latency_ms=40.0,
    )
    assert comparison.legacy_route == "analysis"
    assert comparison.shadow_route == "analysis"
    assert comparison.domain_match is True
    assert comparison.tool_coverage >= 0.5
    assert "metric_vat_burden" in comparison.candidate_tool_ids
    assert comparison.switch_eligible is True
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(ShadowEvaluationRecord))
    assert count == 1


def test_shadow_evaluation_does_not_mutate_legacy_result():
    engine = _engine_with_shadow()
    result = {
        "reply": "ok",
        "function": "score",
        "query_type": "aggregation",
        "data": {"dialog_act": {"act": "analyze", "scenario": "rating"}},
    }
    before = deepcopy(result)
    run_shadow_evaluation_sync(
        engine,
        "综合风险评分多少",
        result,
        legacy_latency_ms=30.0,
    )
    assert result == before


def test_route_mismatch_blocks_switch():
    policy = ConversationPolicy(
        response_mode="social",
        retrieve_candidates=False,
        execute_tools=False,
        allow_analysis=False,
    )
    shadow_route = type("Route", (), {"route": "greeting", "domain": None})()
    comparison = compare_snapshots(
        query="生成财务健康报告",
        legacy=LegacyDialogueSnapshot(
            route="report",
            domain="report",
            function="report",
            query_type=None,
        ),
        shadow_route=shadow_route,
        policy=policy,
        candidate_tool_ids=[],
        legacy_latency_ms=100.0,
        shadow_latency_ms=20.0,
    )
    assert comparison.route_match is False
    assert comparison.switch_eligible is False
    assert any(reason.startswith("route:") for reason in comparison.mismatch_reasons)


def test_analysis_without_candidates_blocks_switch():
    policy = ConversationPolicy(
        response_mode="analysis",
        retrieve_candidates=True,
        execute_tools=True,
        allow_analysis=True,
    )
    shadow_route = type("Route", (), {"route": "analysis", "domain": "warn"})()
    comparison = compare_snapshots(
        query="交税情况",
        legacy=LegacyDialogueSnapshot(
            route="analysis",
            domain="warn",
            function="tax",
            query_type="aggregation",
        ),
        shadow_route=shadow_route,
        policy=policy,
        candidate_tool_ids=[],
        legacy_latency_ms=100.0,
        shadow_latency_ms=20.0,
    )
    assert comparison.switch_eligible is False
    assert "no_candidates" in comparison.mismatch_reasons


def test_legacy_snapshot_maps_report_function():
    snapshot = legacy_snapshot_from_result(
        "生成财务健康报告",
        {
            "function": "report",
            "query_type": None,
            "data": {"dialog_act": {"act": "analyze"}},
        },
    )
    assert snapshot.route == "report"
    assert snapshot.domain == "report"

def test_legacy_clarify_with_shadow_candidates_is_route_compatible():
    policy = ConversationPolicy(
        response_mode="analysis",
        retrieve_candidates=True,
        execute_tools=True,
        allow_analysis=True,
    )
    shadow_route = type("Route", (), {"route": "analysis", "domain": "loan"})()
    comparison = compare_snapshots(
        query="企业4现金流净额怎么样",
        legacy=LegacyDialogueSnapshot(
            route="clarify",
            domain=None,
            function="general",
            query_type=None,
        ),
        shadow_route=shadow_route,
        policy=policy,
        candidate_tool_ids=["metric_cash_flow_net"],
        legacy_latency_ms=100.0,
        shadow_latency_ms=20.0,
    )
    assert comparison.route_match is True
    assert comparison.switch_eligible is True


def test_unknown_entity_overrides_misclassified_analysis_route():
    from app.services.dialog_act import DialogAct

    route = dialog_act_to_raw_route(
        DialogAct(act="analyze", scenario="warn", scope_target="individual", confidence=0.9),
        "看看无此企业发票异常",
    )
    assert route["route"] == "unknown_entity"
    assert route["needs_tools"] is False
