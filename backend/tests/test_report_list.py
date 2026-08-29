"""报告列表与遗留 PDF 清理"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.slice_report import cleanup_legacy_reports, REPORTS_DIR


def test_cleanup_legacy_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.slice_report.REPORTS_DIR", tmp_path)
    (tmp_path / "ENT001_20260703_120000.pdf").write_bytes(b"%PDF")
    (tmp_path / "slice_general_20260826_111552.pdf").write_bytes(b"%PDF")
    (tmp_path / "random_old.pdf").write_bytes(b"%PDF")

    removed = cleanup_legacy_reports()
    assert removed == 2
    assert (tmp_path / "slice_general_20260826_111552.pdf").exists()
    assert not (tmp_path / "ENT001_20260703_120000.pdf").exists()


def test_report_list_slice_and_ent(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr("app.services.slice_report.REPORTS_DIR", tmp_path)
    (tmp_path / "ENT001_20260703_120000.pdf").write_bytes(b"%PDF")
    (tmp_path / "slice_general_20260827_101530.pdf").write_bytes(b"%PDF")
    (tmp_path / "ent_abcd1234_20260827_101531_deadbeef.pdf").write_bytes(b"%PDF")

    client = TestClient(app)
    resp = client.get("/api/v1/report/list")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "slice+ent"
    ids = [it["report_id"] for it in data["items"]]
    assert "slice_general_20260827_101530" in ids
    assert "ent_abcd1234_20260827_101531_deadbeef" in ids
    titles = {it["report_id"]: it["title"] for it in data["items"]}
    assert titles["slice_general_20260827_101530"] == "综合尽调（四类全覆盖） · 2026-08-27 10:15"
    assert not any(id.startswith("ENT") for id in ids)
    assert not (tmp_path / "ENT001_20260703_120000.pdf").exists()
