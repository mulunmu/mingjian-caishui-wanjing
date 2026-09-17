"""Pure block-level mutations for report snapshots."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.services.report_blocks import (
    block_content_hash,
    block_kind_for_claim,
    normalize_report_block,
)


def _blocks_iter(snapshot: dict[str, Any]):
    for chapter in snapshot.get("chapters") or []:
        chapter_key = str(chapter.get("function") or "synthesis")
        for index, block in enumerate(chapter.get("blocks") or []):
            yield chapter, chapter_key, index, normalize_report_block(
                block,
                chapter_key=chapter_key,
                index=index,
            )


def _find_block(snapshot: dict[str, Any], block_id: str):
    for chapter, chapter_key, chapter_index, block in _blocks_iter(snapshot):
        if block.get("block_id") == block_id:
            chapter["blocks"][chapter_index] = block
            return chapter, chapter_key, chapter_index, block
    raise KeyError(f"block not found: {block_id}")


def _ensure_history(snapshot: dict[str, Any], block: dict[str, Any]) -> list[dict[str, Any]]:
    history = snapshot.setdefault("block_versions", {}).setdefault(block["block_id"], [])
    if not history:
        history.append(deepcopy(block))
    return history


def _record_revision(
    snapshot: dict[str, Any],
    *,
    action: str,
    block_id: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    snapshot.setdefault("block_revisions", []).append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "block_id": block_id,
            "before": deepcopy(before),
            "after": deepcopy(after),
        }
    )


def lock_block(snapshot: dict[str, Any], block_id: str, locked: bool = True) -> dict[str, Any]:
    _, _, _, block = _find_block(snapshot, block_id)
    before = deepcopy(block)
    block["locked"] = bool(locked)
    _record_revision(snapshot, action="lock" if locked else "unlock", block_id=block_id, before=before, after=block)
    return block


def move_block(snapshot: dict[str, Any], block_id: str, target_index: int) -> dict[str, Any]:
    chapter, _, _, block = _find_block(snapshot, block_id)
    if block.get("locked"):
        raise ValueError(f"block is locked: {block_id}")
    blocks = chapter.setdefault("blocks", [])
    current_index = next(i for i, item in enumerate(blocks) if item.get("block_id") == block_id)
    target = max(0, min(int(target_index), len(blocks) - 1))
    before = deepcopy(blocks[current_index])
    moved = blocks.pop(current_index)
    blocks.insert(target, moved)
    _record_revision(snapshot, action="move", block_id=block_id, before=before, after=deepcopy(moved))
    return moved


def remove_block(snapshot: dict[str, Any], block_id: str) -> dict[str, Any]:
    _, _, _, block = _find_block(snapshot, block_id)
    if block.get("locked"):
        raise ValueError(f"block is locked: {block_id}")
    before = deepcopy(block)
    history = _ensure_history(snapshot, block)
    block["status"] = "removed"
    block["version"] = int(block.get("version") or 1) + 1
    block["content_hash"] = block_content_hash(block)
    history.append(deepcopy(block))
    _record_revision(snapshot, action="remove", block_id=block_id, before=before, after=block)
    return block


def regenerate_block(snapshot: dict[str, Any], block_id: str) -> dict[str, Any]:
    chapter, chapter_key, _, current = _find_block(snapshot, block_id)
    if current.get("locked"):
        raise ValueError(f"block is locked: {block_id}")
    source_index = current.get("source_claim_index")
    if source_index is None:
        raise ValueError("synthesis block has no Claim source to regenerate")
    claims = chapter.get("claims") or []
    if not isinstance(source_index, int) or source_index >= len(claims):
        raise ValueError("source Claim index is unavailable")
    claim = claims[source_index]
    block_kind = block_kind_for_claim(chapter_key, claim)
    from app.services.report_blocks import _block_title

    value = claim.get("value") or {}
    trace = claim.get("trace") or {}
    before = deepcopy(current)
    history = _ensure_history(snapshot, current)
    rebuilt = {
        **current,
        "type": block_kind,
        "title": _block_title(block_kind, str(value.get("metric") or "")),
        "paragraph": str(claim.get("claim") or "").strip(),
        "metric": str(value.get("metric") or ""),
        "number": value.get("number"),
        "unit": value.get("unit") or "",
        "trace": f"{trace.get('table')}.{trace.get('field')}" if trace.get("table") and trace.get("field") else "",
        "status": "active",
        "version": int(current.get("version") or 1) + 1,
    }
    rebuilt["content_hash"] = block_content_hash(rebuilt)
    copy = dict(rebuilt)
    current.clear()
    current.update(copy)
    history.append(deepcopy(current))
    _record_revision(snapshot, action="regenerate", block_id=block_id, before=before, after=current)
    return current


def restore_block_version(snapshot: dict[str, Any], block_id: str, version: int) -> dict[str, Any]:
    _, _, _, current = _find_block(snapshot, block_id)
    if current.get("locked"):
        raise ValueError(f"block is locked: {block_id}")
    history = _ensure_history(snapshot, current)
    target = next((item for item in history if int(item.get("version") or 1) == int(version)), None)
    if target is None:
        raise KeyError(f"block version not found: {block_id}@{version}")
    before = deepcopy(current)
    max_version = max(int(item.get("version") or 1) for item in history)
    restored = deepcopy(target)
    restored["block_id"] = block_id
    restored["status"] = "active"
    restored["version"] = max_version + 1
    restored["restored_from_version"] = int(version)
    restored["content_hash"] = block_content_hash(restored)
    current.clear()
    current.update(restored)
    history.append(deepcopy(current))
    _record_revision(snapshot, action="restore", block_id=block_id, before=before, after=current)
    return current
