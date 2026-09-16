from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.report_blueprint import ReportBlueprintRecord
from app.schemas.report_blueprint import BlockPlan, ReportBlueprint, ReportScope, SectionPlan
from app.schemas.tool_plan import ToolStep
from app.services.report_blueprint import (
    ReportBlueprintError,
    compile_report_blueprint,
    execute_report_blueprint,
    load_report_blueprint,
    save_report_blueprint,
)
from app.services.report_blueprint_async import execute_report_blueprint_async
from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.tool_rag import load_tool_snapshot_sync
from tests.test_semantic_registry_seed import _engine


def _engine_with_blueprints():
    engine = _engine()
    Base.metadata.create_all(engine, tables=[ReportBlueprintRecord.__table__])
    seed_semantic_registry(engine)
    return engine


def _tool_fns():
    return {
        "metric_debt_ratio": lambda **_: {"metric": "debt_ratio", "value": 0.72},
        "metric_cash_flow_level": lambda **_: {
            "metric": "cash_flow_level",
            "value": "承压",
        },
        "metric_tax_arrears_cnt": lambda **_: {
            "metric": "tax_arrears_cnt",
            "value": 1,
        },
    }


def _blueprint():
    return ReportBlueprint(
        objective="偿债与税务风险",
        scope=ReportScope(sample_mode="entities", entity_ids=["ENT017"]),
        sections=[
            SectionPlan(
                section_id="financial",
                chapter_key="financial",
                objective="偿债能力",
                steps=[
                    ToolStep(
                        step_id="debt",
                        tool_id="metric_debt_ratio",
                        params={"entity": "ENT017"},
                    ),
                    ToolStep(
                        step_id="cash",
                        tool_id="metric_cash_flow_level",
                        params={"entity": "ENT017"},
                        depends_on=["debt"],
                    ),
                ],
                blocks=[
                    BlockPlan(
                        block_id="debt-kpi",
                        kind="kpi",
                        title="资产负债率",
                        source_tool_id="metric_debt_ratio",
                    ),
                    BlockPlan(
                        block_id="cash-kpi",
                        kind="kpi",
                        title="现金流水平",
                        source_tool_id="metric_cash_flow_level",
                    ),
                ],
            ),
            SectionPlan(
                section_id="tax",
                chapter_key="tax",
                objective="税务风险",
                steps=[
                    ToolStep(
                        step_id="arrears",
                        tool_id="metric_tax_arrears_cnt",
                        params={"entity": "ENT017"},
                    )
                ],
                blocks=[
                    BlockPlan(
                        block_id="arrears-kpi",
                        kind="kpi",
                        title="欠税记录",
                        source_tool_id="metric_tax_arrears_cnt",
                    )
                ],
            ),
        ],
    )


def test_compile_rejects_empty_blueprint():
    engine = _engine_with_blueprints()
    blueprint = ReportBlueprint(objective="empty")
    with pytest.raises(ReportBlueprintError, match="at least one section"):
        compile_report_blueprint(blueprint, load_tool_snapshot_sync(engine))


def test_compile_rejects_unknown_chapter():
    engine = _engine_with_blueprints()
    blueprint = ReportBlueprint(
        objective="bad",
        sections=[
            SectionPlan(
                section_id="bad",
                chapter_key="missing",
                steps=[],
                blocks=[],
            )
        ],
    )
    with pytest.raises(ReportBlueprintError, match="unknown chapter"):
        compile_report_blueprint(blueprint, load_tool_snapshot_sync(engine))


def test_compile_rejects_block_referencing_tool_outside_section():
    engine = _engine_with_blueprints()
    blueprint = ReportBlueprint(
        objective="bad block",
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
                        block_id="bad",
                        kind="kpi",
                        source_tool_id="metric_tax_arrears_cnt",
                    )
                ],
            )
        ],
    )
    with pytest.raises(ReportBlueprintError, match="references tool not in section"):
        compile_report_blueprint(blueprint, load_tool_snapshot_sync(engine))


def test_execute_blueprint_is_deterministic_and_chapter_isolated():
    engine = _engine_with_blueprints()
    snapshot = load_tool_snapshot_sync(engine)
    compiled = compile_report_blueprint(_blueprint(), snapshot)
    first = execute_report_blueprint(compiled, snapshot, _tool_fns())
    second = execute_report_blueprint(compiled, snapshot, _tool_fns())
    assert first == second
    assert [claim["metric"] for claim in first.sections["financial"].claims] == [
        "debt_ratio",
        "cash_flow_level",
    ]
    assert [claim["metric"] for claim in first.sections["tax"].claims] == [
        "tax_arrears_cnt"
    ]


def test_blueprint_persistence_roundtrip_and_rerun():
    engine = _engine_with_blueprints()
    snapshot = load_tool_snapshot_sync(engine)
    with Session(engine) as session:
        record = save_report_blueprint(
            session,
            _blueprint(),
            owner="owner@example.com",
            session_id="session-1",
        )
        session.commit()
        blueprint_id = record.blueprint_id

    with Session(engine) as session:
        loaded = load_report_blueprint(session, blueprint_id)
    assert loaded is not None
    assert loaded.blueprint_id == blueprint_id
    assert loaded.objective == "偿债与税务风险"
    compiled = compile_report_blueprint(loaded, snapshot)
    execution = execute_report_blueprint(compiled, snapshot, _tool_fns())
    assert execution.blueprint_id == blueprint_id
    assert set(execution.sections) == {"financial", "tax"}


@pytest.mark.asyncio
async def test_async_blueprint_execution_matches_sync_result():
    engine = _engine_with_blueprints()
    snapshot = load_tool_snapshot_sync(engine)
    compiled = compile_report_blueprint(_blueprint(), snapshot)
    sync_result = execute_report_blueprint(compiled, snapshot, _tool_fns())
    async_result = await execute_report_blueprint_async(
        compiled,
        snapshot,
        _tool_fns(),
        max_concurrency=2,
    )
    assert async_result == sync_result
