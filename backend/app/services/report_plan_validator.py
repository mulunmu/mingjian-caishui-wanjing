"""Validate report blocks against chapter and Claim contracts."""
from __future__ import annotations

from app.schemas.report_plan import (
    ReportPlan,
    ReportPlanValidationError,
    ReportPlanValidationReport,
)
from app.services.report_blocks import BLOCK_KINDS, normalize_chapter_key, supports_block_kind


def _error(code: str, message: str, *, chapter_id=None, block_id=None):
    return ReportPlanValidationError(
        code=code,
        message=message,
        chapter_id=chapter_id,
        block_id=block_id,
    )


def validate_report_plan(plan: ReportPlan) -> ReportPlanValidationReport:
    errors = []
    warnings = []
    chapter_ids: set[str] = set()
    block_ids: set[str] = set()
    if not plan.chapters:
        errors.append(_error("plan_empty", "report plan has no chapters"))
    for chapter in plan.chapters:
        if chapter.chapter_id in chapter_ids:
            errors.append(_error("duplicate_chapter_id", chapter.chapter_id, chapter_id=chapter.chapter_id))
        chapter_ids.add(chapter.chapter_id)
        chapter_key = normalize_chapter_key(chapter.module_key)
        if not chapter.blocks:
            errors.append(_error("chapter_without_blocks", chapter.chapter_id, chapter_id=chapter.chapter_id))
        for block in chapter.blocks:
            if block.block_id in block_ids:
                errors.append(_error("duplicate_block_id", block.block_id, block_id=block.block_id))
            block_ids.add(block.block_id)
            if block.block_kind not in BLOCK_KINDS:
                errors.append(_error("block_kind_unknown", block.block_kind, block_id=block.block_id))
            elif not supports_block_kind(chapter_key, block.block_kind):
                errors.append(
                    _error(
                        "block_kind_incompatible",
                        f"{block.block_kind} is not compatible with {chapter_key}",
                        chapter_id=chapter.chapter_id,
                        block_id=block.block_id,
                    )
                )
            if not block.metric_keys and block.block_kind != "synthesis_paragraph":
                warnings.append(_error("metric_missing", block.block_id, block_id=block.block_id))
    return ReportPlanValidationReport(valid=not errors, errors=errors, warnings=warnings)
