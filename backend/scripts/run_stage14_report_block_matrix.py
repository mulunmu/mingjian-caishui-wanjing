"""Run the 30+ chapter/block report composition matrix through shared renderers."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.services import slice_report
from app.services.report_blocks import build_report_block_compatibility_report
from app.services.report_html import build_report_html


def _claim_for(block_kind: str) -> dict:
    if block_kind == "trend_paragraph":
        return {
            "claim": "营收同比增长 5%。",
            "value": {"metric": "revenue_yoy", "number": 5, "unit": "%"},
            "trace": {"table": "core_metrics", "field": "revenue_yoy"},
        }
    if block_kind == "comparison_paragraph":
        return {
            "claim": "资产负债率高于行业均值 10 个百分点。",
            "value": {"metric": "debt_ratio_gap", "number": 10, "unit": "%"},
            "trace": {"table": "industry_benchmark", "field": "debt_ratio"},
        }
    return {
        "claim": "资产负债率为 72%。",
        "value": {"metric": "debt_ratio", "number": 72, "unit": "%"},
        "trace": {"table": "core_metrics", "field": "debt_ratio"},
    }


def run() -> dict:
    matrix = build_report_block_compatibility_report()
    results: list[dict] = []
    failures: list[dict] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        original = slice_report.REPORTS_DIR
        slice_report.REPORTS_DIR = Path(temp_dir)
        try:
            for index, (chapter_key, block_kind) in enumerate(
                matrix["compatible_pairs"], start=1
            ):
                report_id = f"stage14-block-{index:02d}"
                context = {
                    "scenario": chapter_key,
                    "title": f"{chapter_key} block matrix",
                    "subtitle": "",
                    "report_date": "2026年09月17日",
                    "summary_kpis": [],
                    "executive_summary": "组合矩阵验证",
                    "chapters": [
                        {
                            "title": f"{chapter_key} chapter",
                            "purpose": "block matrix",
                            "function": chapter_key,
                            "claims": [_claim_for(block_kind)],
                            "narration": "综合研判：组合结果已生成。",
                            "numeric_rows": [],
                        }
                    ],
                    "validation": {"ok": True},
                }
                try:
                    slice_report._attach_chapter_blocks(context["chapters"])
                    slice_report.write_report_snapshot(report_id, context)
                    snapshot = slice_report.read_report_snapshot(report_id)
                    if snapshot is None:
                        raise AssertionError("snapshot missing")
                    detail = slice_report.build_report_detail(report_id, snapshot)
                    html = build_report_html(snapshot, report_id)
                    block_types = [
                        str(block.get("type") or "")
                        for block in detail["chapters"][0]["blocks"]
                    ]
                    if block_kind not in block_types:
                        raise AssertionError(f"missing block kind {block_kind}")
                    for block in detail["chapters"][0]["blocks"]:
                        if block["paragraph"] not in html:
                            raise AssertionError("api/html block paragraph mismatch")
                    results.append(
                        {
                            "chapter": chapter_key,
                            "block_kind": block_kind,
                            "block_types": block_types,
                            "ok": True,
                        }
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "chapter": chapter_key,
                            "block_kind": block_kind,
                            "error": str(exc),
                        }
                    )
        finally:
            slice_report.REPORTS_DIR = original
    return {
        "total": len(matrix["compatible_pairs"]),
        "passed": len(results),
        "failed": len(failures),
        "failures": failures,
        "results": results,
    }


def main() -> None:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
