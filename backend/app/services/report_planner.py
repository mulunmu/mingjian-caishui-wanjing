"""Build and bind a structured report plan from chapter-level claims."""
from __future__ import annotations

import hashlib
from typing import Any

from app.schemas.custom_report import CustomReportSpec
from app.schemas.report_plan import ReportBlock, ReportChapter, ReportPlan
from app.services.report_blocks import build_chapter_blocks


_PATTERN_BLOCK_KIND = {
    "trend": "trend_paragraph",
    "attribution": "synthesis_paragraph",
    "comparison": "comparison_paragraph",
    "benchmark": "comparison_paragraph",
    "ranking": "comparison_paragraph",
    "contribution": "comparison_paragraph",
    "stratification": "comparison_paragraph",
    "structure": "comparison_paragraph",
    "distribution": "comparison_paragraph",
    "anomaly": "comparison_paragraph",
}


def _plan_id(report_spec: dict[str, Any]) -> str:
    payload = repr(
        [
            report_spec.get("title"),
            [
                (chapter.get("module_key"), chapter.get("analysis_patterns"))
                for chapter in report_spec.get("chapters") or []
            ],
        ]
    )
    return "report-plan-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _block_kind(patterns: list[str]) -> str:
    for pattern in patterns or []:
        if pattern in _PATTERN_BLOCK_KIND:
            return _PATTERN_BLOCK_KIND[pattern]
    return "metric_paragraph"


def build_report_plan_from_report_spec(report_spec: dict[str, Any]) -> ReportPlan:
    chapters = []
    for index, chapter in enumerate(report_spec.get("chapters") or [], start=1):
        module_key = str(chapter.get("module_key") or chapter.get("function") or f"chapter_{index}")
        patterns = [str(item) for item in chapter.get("analysis_patterns") or []]
        kind = _block_kind(patterns)
        metrics = [str(item) for item in chapter.get("metric_allowlist") or [] if item]
        metric_slots = metrics or [f"{module_key}_overview"]
        blocks = [
            ReportBlock(
                block_id=f"{module_key}-block-{metric_index}",
                block_kind=kind,
                title=chapter.get("title") or module_key,
                metric_keys=[metric] if metrics else [],
                filters={},
                status="planned",
            )
            for metric_index, metric in enumerate(metric_slots, start=1)
        ]
        chapters.append(
            ReportChapter(
                chapter_id=f"{module_key}-{index}",
                module_key=module_key,
                title=str(chapter.get("title") or module_key),
                purpose=str(chapter.get("purpose") or ""),
                analysis_patterns=patterns,
                blocks=blocks,
            )
        )
    return ReportPlan(
        plan_id=_plan_id(report_spec),
        report_mode="custom",
        title=str(report_spec.get("title") or "定制风控报告"),
        purpose=str(report_spec.get("purpose") or report_spec.get("governing_question") or ""),
        scope={
            "industry_l1": report_spec.get("industry_l1"),
            "province": report_spec.get("province"),
            "enterprises": report_spec.get("enterprises") or [],
        },
        chapters=chapters,
        metadata={"source": "custom_report_spec"},
    )


def build_report_plan(spec: CustomReportSpec) -> ReportPlan:
    from app.services.custom_report import normalize_spec, spec_to_report_spec

    normalized = normalize_spec(spec) or spec
    return build_report_plan_from_report_spec(spec_to_report_spec(normalized))


def _claim_id(claim: dict[str, Any], index: int) -> str:
    trace = claim.get("trace") if isinstance(claim, dict) else None
    if isinstance(trace, dict) and trace.get("query_id"):
        return str(trace["query_id"])
    return f"claim-{index}"


def bind_report_plan_claims(
    plan: ReportPlan,
    chapters: list[dict[str, Any]],
) -> ReportPlan:
    chapter_map: dict[str, dict[str, Any]] = {}
    for chapter in chapters:
        for key in (chapter.get("module_key"), chapter.get("function"), chapter.get("title")):
            if key:
                chapter_map[str(key)] = chapter
    output_chapters: list[ReportChapter] = []
    for chapter in plan.chapters:
        source = chapter_map.get(chapter.module_key) or chapter_map.get(chapter.chapter_id) or {}
        raw_claims = [claim for claim in source.get("claims") or [] if isinstance(claim, dict)]
        generated_blocks = build_chapter_blocks(source) if source else []
        claim_index = {_claim_id(claim, i): claim for i, claim in enumerate(raw_claims, start=1)}
        blocks: list[ReportBlock] = []
        for block in chapter.blocks:
            matching = [
                generated
                for generated in generated_blocks
                if generated.get("type") == block.block_kind
            ]
            metric_set = set(block.metric_keys)
            claim_ids: list[str] = []
            for generated in matching:
                metric = str(generated.get("metric") or "")
                if metric_set and metric and metric not in metric_set:
                    continue
                source_index = generated.get("source_claim_index")
                if isinstance(source_index, int) and 0 <= source_index < len(raw_claims):
                    claim_ids.append(_claim_id(raw_claims[source_index], source_index + 1))
            if not claim_ids and not metric_set:
                claim_ids = list(claim_index)[:1]
            blocks.append(
                block.model_copy(
                    update={
                        "claim_ids": list(dict.fromkeys(claim_ids)),
                        "status": "ready" if claim_ids else "missing",
                    }
                )
            )
        output_chapters.append(chapter.model_copy(update={"blocks": blocks}))
    return plan.model_copy(update={"chapters": output_chapters})
