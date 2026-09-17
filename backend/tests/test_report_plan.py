from __future__ import annotations

from app.schemas.custom_report import CustomReportSpec
from app.schemas.report_plan import ReportBlock, ReportChapter, ReportPlan
from app.services.report_plan_validator import validate_report_plan
from app.services.report_planner import bind_report_plan_claims, build_report_plan
from app.services.custom_report import spec_to_report_spec


def test_report_plan_expands_custom_spec_into_chapter_blocks():
    spec = CustomReportSpec(
        chapters=["financial", "tax"],
        title="财务税务组合报告",
        purpose="检查财务和税务风险",
        chapter_analyses={
            "financial": ["trend", "benchmark"],
            "tax": ["anomaly"],
        },
    )

    plan = build_report_plan(spec)

    assert plan.report_mode == "custom"
    assert [chapter.module_key for chapter in plan.chapters] == ["financial", "tax"]
    assert plan.chapters[0].blocks[0].block_kind == "trend_paragraph"
    assert plan.chapters[1].blocks[0].block_kind == "comparison_paragraph"
    assert all(block.status == "planned" for chapter in plan.chapters for block in chapter.blocks)


def test_report_plan_validator_rejects_incompatible_block_kind():
    plan = ReportPlan(
        plan_id="plan-invalid",
        report_mode="custom",
        title="invalid",
        chapters=[
            ReportChapter(
                chapter_id="tax",
                module_key="tax",
                title="税务",
                blocks=[
                    ReportBlock(
                        block_id="tax-trend",
                        block_kind="trend_paragraph",
                        title="税务趋势",
                        metric_keys=["tax_on_time_rate"],
                    )
                ],
            )
        ],
    )

    report = validate_report_plan(plan)

    assert report.valid is False
    assert any(error.code == "block_kind_incompatible" for error in report.errors)


def test_report_plan_binds_claim_ids_to_matching_blocks():
    plan = ReportPlan(
        plan_id="plan-bind",
        report_mode="custom",
        title="绑定测试",
        chapters=[
            ReportChapter(
                chapter_id="financial",
                module_key="financial",
                title="财务",
                blocks=[
                    ReportBlock(
                        block_id="financial-metric",
                        block_kind="metric_paragraph",
                        title="资产负债率",
                        metric_keys=["debt_ratio"],
                    )
                ],
            )
        ],
    )
    chapters = [
        {
            "module_key": "financial",
            "function": "financial",
            "claims": [
                {
                    "claim": "资产负债率 80%。",
                    "value": {"metric": "debt_ratio", "number": 80, "unit": "%"},
                    "trace": {"table": "core_metrics", "field": "debt_ratio", "query_id": "Q-debt"},
                }
            ],
        }
    ]

    bound = bind_report_plan_claims(plan, chapters)

    block = bound.chapters[0].blocks[0]
    assert block.claim_ids == ["Q-debt"]
    assert block.status == "ready"


def test_custom_report_spec_contains_compiled_report_plan():
    spec = CustomReportSpec(chapters=["financial"], title="财务报告")

    report_spec = spec_to_report_spec(spec)

    assert report_spec["report_plan"]["report_mode"] == "custom"
    assert report_spec["report_plan"]["chapters"][0]["module_key"] == "financial"
