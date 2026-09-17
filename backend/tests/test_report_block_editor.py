from __future__ import annotations

import pytest

from app.services.report_block_editor import (
    lock_block,
    move_block,
    regenerate_block,
    remove_block,
    restore_block_version,
)
from app.services.report_blocks import block_content_hash, build_chapter_blocks


def _snapshot():
    chapter = {
        "function": "financial",
        "title": "财务",
        "claims": [
            {"claim": "流动比率偏低。", "value": {"metric": "current_ratio", "number": 0.8, "unit": ""}, "trace": {"table": "core_metrics", "field": "current_ratio"}},
            {"claim": "流动比率同比下降。", "value": {"metric": "revenue_yoy", "number": -0.2, "unit": "%"}, "trace": {"table": "core_metrics", "field": "revenue_yoy"}},
        ],
        "narration": "整体偿债能力承压。",
    }
    chapter["blocks"] = build_chapter_blocks(chapter)
    return {"chapters": [chapter], "block_tree_version": "2"}


def test_blocks_have_stable_identity_and_hash():
    snapshot = _snapshot()
    blocks = snapshot["chapters"][0]["blocks"]
    assert [block["block_id"].split("-")[0] for block in blocks] == ["financial"] * 3
    assert len({block["block_id"] for block in blocks}) == 3
    assert all(block["content_hash"] == block_content_hash(block) for block in blocks)


def test_locked_block_cannot_regenerate_or_move():
    snapshot = _snapshot()
    block_id = snapshot["chapters"][0]["blocks"][0]["block_id"]
    lock_block(snapshot, block_id, True)
    with pytest.raises(ValueError, match="locked"):
        regenerate_block(snapshot, block_id)
    with pytest.raises(ValueError, match="locked"):
        move_block(snapshot, block_id, 2)


def test_move_remove_and_restore_block_version():
    snapshot = _snapshot()
    block_id = snapshot["chapters"][0]["blocks"][0]["block_id"]
    original_version = snapshot["chapters"][0]["blocks"][0]["version"]
    move_block(snapshot, block_id, 2)
    assert snapshot["chapters"][0]["blocks"][2]["block_id"] == block_id
    remove_block(snapshot, block_id)
    removed = next(block for block in snapshot["chapters"][0]["blocks"] if block["block_id"] == block_id)
    assert removed["status"] == "removed"
    restore_block_version(snapshot, block_id, original_version)
    restored = next(block for block in snapshot["chapters"][0]["blocks"] if block["block_id"] == block_id)
    assert restored["status"] == "active"
    assert snapshot["block_revisions"]
