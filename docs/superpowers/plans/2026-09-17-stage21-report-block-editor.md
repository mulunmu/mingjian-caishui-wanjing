# Stage 21 Report Block Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every report paragraph block a stable identity and revision history, and support block-level lock, reorder, soft-delete, regenerate and restore without allowing free-text facts.

**Architecture:** Keep the existing chapter/Claim/Block tree. Upgrade the snapshot to block-tree version 2 with block IDs, versions, content hashes and revisions. Mutations operate only on stored Claim-derived blocks and atomically rewrite the snapshot.

**Tech Stack:** Python dataclasses/pure functions, JSON report snapshots, FastAPI authenticated endpoints, WeasyPrint renderer.

---

### Task 1: Stable Block Identity And Version Metadata

**Files:**
- Modify: `backend/app/services/report_blocks.py`
- Modify: `backend/app/services/slice_report.py`
- Test: `backend/tests/test_report_block_editor.py`, `backend/tests/test_report_blocks.py`

- [x] Assign every block a stable `block_id`, `version`, `content_hash`, `status`, `locked` and `source_claim_index`.
- [x] Upgrade snapshots from `block_tree_version=1` to `2`.
- [x] Keep old snapshots readable by normalizing missing metadata on read.
- [x] Add tests for stable IDs and hash changes.
- [x] Commit block identity.

### Task 2: Pure Block Mutation Service

**Files:**
- Create: `backend/app/services/report_block_editor.py`
- Test: `backend/tests/test_report_block_editor.py`

- [x] Implement `lock_block`, `move_block`, `remove_block`, `regenerate_block` and `restore_block_version` as pure snapshot mutations.
- [x] Every mutation appends a revision with timestamp, action, version and before/after block data.
- [x] Locked blocks cannot be regenerated, moved or removed until unlocked.
- [x] Regeneration can only rebuild from the original Claim index and cannot accept arbitrary paragraph text.
- [x] Commit the editor service.

### Task 3: Atomic Snapshot Updates And API

**Files:**
- Modify: `backend/app/services/slice_report.py`
- Modify: `backend/app/api/v1/report.py`
- Test: `backend/tests/test_report_block_api.py`

- [x] Add atomic `update_report_snapshot(report_id, mutator)` with process-local per-report locking.
- [x] Add authenticated block mutation/restore endpoints.
- [x] Return the updated structured report detail and preserve existing report permissions.
- [x] Re-render the PDF from the updated block tree when possible; never silently claim success when rendering fails.
- [x] Commit snapshot API.

### Task 4: Renderer Consistency

**Files:**
- Modify: `backend/app/templates/slice_report.html` if needed.
- Test: `backend/tests/test_report_blocks.py`, `backend/tests/test_report_block_api.py`

- [x] Ensure API, HTML and PDF all read `chapters[].blocks` in the same order.
- [x] Hidden or removed blocks stay in revision history but are not rendered.
- [x] Report detail exposes block version metadata but not internal Claim tables beyond existing trace fields.
- [x] Commit renderer consistency.

### Task 5: Closure Evidence

- [x] Create `报告/阶段21-报告Block编辑闭环报告.md`.
- [x] Run block editor tests, full regression, report block matrix and two 105-case matrices.
- [x] Verify a locked block cannot be mutated and a restored block returns to its prior version.
- [x] Tag `rag-v2-stage21-accepted-20260917` only after all gates pass.
