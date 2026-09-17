"""Chapter/block contracts and Claim-derived paragraph block assembly."""
from __future__ import annotations

import os
import re
import hashlib
from typing import Any


BLOCK_KINDS = (
    "metric_paragraph",
    "comparison_paragraph",
    "trend_paragraph",
    "synthesis_paragraph",
)
LEGACY_BLOCK_KINDS = ("kpi", "chart", "table", "narrative")

CHAPTER_BLOCK_KINDS: dict[str, set[str]] = {
    "score": set(BLOCK_KINDS),
    "financial": set(BLOCK_KINDS),
    "tax": {"metric_paragraph", "synthesis_paragraph"},
    "fraud": {"metric_paragraph", "comparison_paragraph", "synthesis_paragraph"},
    "authenticity": set(BLOCK_KINDS),
    "benchmark": set(BLOCK_KINDS),
    "trend": set(BLOCK_KINDS),
    "signal": set(BLOCK_KINDS),
    "synthesis": {"metric_paragraph", "synthesis_paragraph"},
}

_TREND_METRICS = {
    "revenue_yoy",
    "profit_yoy",
    "tax_yoy",
    "invoice_yoy",
    "change_rate",
    "trend_gap",
}
_COMPARISON_RE = re.compile(r"对比|相比|高于|低于|高于均值|低于均值|同业|行业均值|差距|优于|劣于")
_TREND_RE = re.compile(r"同比|环比|趋势|上升|下降|增长|回落|增速|变化")


def report_block_tree_enabled() -> bool:
    return os.getenv("REPORT_BLOCK_TREE_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }


def normalize_chapter_key(chapter_key: str | None) -> str:
    key = (chapter_key or "synthesis").strip().lower()
    return key if key in CHAPTER_BLOCK_KINDS else "synthesis"


def supports_block_kind(chapter_key: str | None, block_kind: str) -> bool:
    if block_kind in LEGACY_BLOCK_KINDS:
        return True
    return block_kind in CHAPTER_BLOCK_KINDS[normalize_chapter_key(chapter_key)]


def _claim_text(claim: dict[str, Any]) -> str:
    return str(claim.get("claim") or "").strip()


def _claim_metric(claim: dict[str, Any]) -> str:
    return str((claim.get("value") or {}).get("metric") or "")


def block_kind_for_claim(chapter_key: str | None, claim: dict[str, Any]) -> str:
    key = normalize_chapter_key(chapter_key)
    text = _claim_text(claim)
    metric = _claim_metric(claim)
    if metric in _TREND_METRICS or _TREND_RE.search(text):
        candidate = "trend_paragraph"
    elif _COMPARISON_RE.search(text):
        candidate = "comparison_paragraph"
    else:
        candidate = "metric_paragraph"
    if supports_block_kind(key, candidate):
        return candidate
    return "metric_paragraph"


def _metric_title(metric: str) -> str:
    from app.services.metric_registry import RUNTIME_METRIC_LABELS

    return RUNTIME_METRIC_LABELS.get(metric, metric or "指标结论")


def _block_title(block_kind: str, metric: str) -> str:
    if block_kind == "comparison_paragraph":
        return f"{_metric_title(metric)}对比" if metric else "对比结论"
    if block_kind == "trend_paragraph":
        return f"{_metric_title(metric)}趋势" if metric else "趋势结论"
    return _metric_title(metric)


def block_content_hash(block: dict[str, Any]) -> str:
    content = "|".join(
        [
            str(block.get("type") or ""),
            str(block.get("title") or ""),
            str(block.get("paragraph") or ""),
            str(block.get("metric") or ""),
            str(block.get("number") if block.get("number") is not None else ""),
            str(block.get("unit") or ""),
            str(block.get("trace") or ""),
        ]
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize_report_block(
    block: dict[str, Any],
    *,
    chapter_key: str,
    index: int,
) -> dict[str, Any]:
    out = dict(block)
    out["block_id"] = str(
        out.get("block_id")
        or f"{normalize_chapter_key(chapter_key)}-{index + 1}-{out.get('type') or 'metric_paragraph'}"
    )
    out["version"] = int(out.get("version") or 1)
    out["status"] = str(out.get("status") or "active")
    out["locked"] = bool(out.get("locked") or False)
    out.setdefault("source_claim_index", None)
    out["content_hash"] = str(out.get("content_hash") or block_content_hash(out))
    return out


def build_chapter_blocks(chapter: dict[str, Any]) -> list[dict[str, Any]]:
    chapter_key = str(chapter.get("function") or "synthesis")
    blocks: list[dict[str, Any]] = []
    for index, claim in enumerate(chapter.get("claims") or []):
        paragraph = _claim_text(claim)
        if not paragraph:
            continue
        value = claim.get("value") or {}
        metric = _claim_metric(claim)
        trace = claim.get("trace") or {}
        block_kind = (
            block_kind_for_claim(chapter_key, claim)
            if report_block_tree_enabled()
            else "metric_paragraph"
        )
        blocks.append(
            normalize_report_block(
                {
                "type": block_kind,
                "title": _block_title(block_kind, metric),
                "paragraph": paragraph,
                "metric": metric,
                "number": value.get("number"),
                "unit": value.get("unit") or "",
                "trace": (
                    f"{trace.get('table')}.{trace.get('field')}"
                    if trace.get("table") and trace.get("field")
                    else ""
                ),
                "source_claim_index": index,
                },
                chapter_key=chapter_key,
                index=index,
            )
        )
    narration = str(chapter.get("narration") or "").strip()
    if narration:
        blocks.append(
            normalize_report_block(
                {
                "type": "synthesis_paragraph",
                "title": "综合研判",
                "paragraph": narration,
                "metric": "",
                "trace": "",
                "source_claim_index": None,
                },
                chapter_key=chapter_key,
                index=len(blocks),
            )
        )
    return blocks


def validate_report_block_kinds(
    chapter_key: str | None,
    block_kinds: list[str],
) -> list[str]:
    return [
        kind
        for kind in block_kinds
        if not supports_block_kind(chapter_key, kind)
    ]


def build_report_block_compatibility_report() -> dict[str, Any]:
    pairs = [
        (chapter_key, block_kind)
        for chapter_key, allowed in CHAPTER_BLOCK_KINDS.items()
        for block_kind in BLOCK_KINDS
        if block_kind in allowed
    ]
    return {
        "chapters": sorted(CHAPTER_BLOCK_KINDS),
        "block_kinds": list(BLOCK_KINDS),
        "compatible_pair_count": len(pairs),
        "compatible_pairs": pairs,
        "missing": [],
    }
