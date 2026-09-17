from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import slice_report
from app.services.auth_service import create_access_token
from app.services.report_blocks import build_chapter_blocks


def _headers() -> dict[str, str]:
    token = create_access_token("admin@example.com", "admin", "subscriber")
    return {"Authorization": f"Bearer {token}"}


def _snapshot():
    chapter = {
        "function": "financial",
        "title": "财务",
        "claims": [
            {"claim": "流动比率偏低。", "value": {"metric": "current_ratio", "number": 0.8, "unit": ""}, "trace": {"table": "core_metrics", "field": "current_ratio"}},
        ],
        "narration": "整体偿债能力承压。",
    }
    chapter["blocks"] = build_chapter_blocks(chapter)
    return {"scenario": "slice", "title": "测试", "chapters": [chapter], "block_tree_version": "2"}


def test_block_api_lock_regenerate_and_restore(tmp_path, monkeypatch):
    monkeypatch.setattr(slice_report, "REPORTS_DIR", tmp_path)
    snapshot = _snapshot()
    slice_report.write_report_snapshot("block-api", snapshot)
    block_id = snapshot["chapters"][0]["blocks"][0]["block_id"]
    from app.main import app

    client = TestClient(app)
    headers = _headers()
    listed = client.get("/api/v1/report/block-api/blocks", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["blocks"][0]["block_id"] == block_id

    locked = client.patch(
        f"/api/v1/report/block-api/blocks/{block_id}",
        headers=headers,
        json={"locked": True},
    )
    assert locked.status_code == 200
    assert locked.json()["chapters"][0]["blocks"][0]["locked"] is True

    rejected = client.post(
        f"/api/v1/report/block-api/blocks/{block_id}/regenerate",
        headers=headers,
    )
    assert rejected.status_code == 409

    unlocked = client.patch(
        f"/api/v1/report/block-api/blocks/{block_id}",
        headers=headers,
        json={"locked": False},
    )
    assert unlocked.status_code == 200
    regenerated = client.post(
        f"/api/v1/report/block-api/blocks/{block_id}/regenerate",
        headers=headers,
    )
    assert regenerated.status_code == 200
    restored = client.post(
        f"/api/v1/report/block-api/blocks/{block_id}/restore",
        headers=headers,
        json={"version": 1},
    )
    assert restored.status_code == 200
    assert restored.json()["chapters"][0]["blocks"][0]["version"] >= 2

    removed = client.patch(
        f"/api/v1/report/block-api/blocks/{block_id}",
        headers=headers,
        json={"status": "removed"},
    )
    assert removed.status_code == 200
    detail = client.get("/api/v1/report/block-api", headers=headers)
    assert detail.status_code == 200
    assert all(block["block_id"] != block_id for block in detail.json()["chapters"][0]["blocks"])
