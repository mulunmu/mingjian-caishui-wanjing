from __future__ import annotations

from app.services import slice_report
from app.services.report_blocks import (
    build_chapter_blocks,
    build_report_block_compatibility_report,
    validate_report_block_kinds,
)
from app.services.report_html import build_report_html


def test_report_block_compatibility_covers_more_than_thirty_pairs():
    report = build_report_block_compatibility_report()
    assert report["compatible_pair_count"] >= 30
    assert report["missing"] == []
    assert set(report["block_kinds"]) == {
        "metric_paragraph",
        "comparison_paragraph",
        "trend_paragraph",
        "synthesis_paragraph",
    }


def test_claim_types_become_metric_comparison_trend_and_synthesis_blocks():
    chapter = {
        "function": "benchmark",
        "claims": [
            {
                "claim": "资产负债率为 72%。",
                "value": {"metric": "debt_ratio", "number": 72, "unit": "%"},
                "trace": {"table": "core_metrics", "field": "debt_ratio"},
            },
            {
                "claim": "资产负债率高于行业均值 10 个百分点。",
                "value": {"metric": "debt_ratio_gap", "number": 10, "unit": "pct"},
                "trace": {"table": "industry_benchmark", "field": "debt_ratio"},
            },
            {
                "claim": "营收同比增长 5%。",
                "value": {"metric": "revenue_yoy", "number": 5, "unit": "%"},
                "trace": {"table": "core_metrics", "field": "revenue_yoy"},
            },
        ],
        "narration": "综合判断，偿债压力需要继续关注。",
    }
    blocks = build_chapter_blocks(chapter)
    assert [block["type"] for block in blocks] == [
        "metric_paragraph",
        "comparison_paragraph",
        "trend_paragraph",
        "synthesis_paragraph",
    ]
    assert blocks[-1]["paragraph"] == chapter["narration"]


def test_chapter_block_contract_rejects_cross_scenario_kind():
    assert validate_report_block_kinds("tax", ["trend_paragraph"]) == [
        "trend_paragraph"
    ]
    assert validate_report_block_kinds("financial", ["trend_paragraph"]) == []


def test_report_block_tree_rollback_flag_restores_legacy_blocks(monkeypatch):
    monkeypatch.setenv("REPORT_BLOCK_TREE_ENABLED", "false")
    chapter = {
        "function": "trend",
        "claims": [
            {
                "claim": "营收同比增长 5%。",
                "value": {"metric": "revenue_yoy", "number": 5, "unit": "%"},
                "trace": {"table": "core_metrics", "field": "revenue_yoy"},
            }
        ],
        "narration": "综合判断。",
    }
    assert [block["type"] for block in build_chapter_blocks(chapter)] == [
        "metric_paragraph",
        "synthesis_paragraph",
    ]


def test_snapshot_api_and_html_share_same_block_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(slice_report, "REPORTS_DIR", tmp_path)
    context = {
        "scenario": "fraud",
        "title": "测试报告",
        "subtitle": "",
        "report_date": "2026年09月17日",
        "summary_kpis": [],
        "executive_summary": "摘要",
        "chapters": [
            {
                "title": "发票异常",
                "purpose": "发票异常指标",
                "function": "fraud",
                "claims": [
                    {
                        "claim": "红字发票占比为 18%。",
                        "value": {
                            "metric": "red_invoice_ratio",
                            "number": 18,
                            "unit": "%",
                        },
                        "trace": {
                            "table": "invoice",
                            "field": "red_invoice_ratio",
                        },
                    }
                ],
                "narration": "建议核查进销项匹配关系。",
                "numeric_rows": [],
            }
        ],
        "validation": {"ok": True},
    }
    slice_report._attach_chapter_blocks(context["chapters"])
    slice_report.write_report_snapshot("block-tree-test", context)
    snapshot = slice_report.read_report_snapshot("block-tree-test")
    assert snapshot is not None
    assert snapshot["block_tree_version"] == "1"

    detail = slice_report.build_report_detail("block-tree-test", snapshot)
    assert detail["block_tree_version"] == "1"
    api_blocks = detail["chapters"][0]["blocks"]
    snapshot_blocks = snapshot["chapters"][0]["blocks"]
    assert api_blocks == snapshot_blocks
    assert [block["type"] for block in api_blocks] == [
        "metric_paragraph",
        "synthesis_paragraph",
    ]

    html = build_report_html(snapshot, "block-tree-test")
    for block in api_blocks:
        assert block["paragraph"] in html
