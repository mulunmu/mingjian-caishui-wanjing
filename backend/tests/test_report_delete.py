"""报告删除 — 纯单元测试（tmp_path + monkeypatch，不碰真库）。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.slice_report import delete_report, get_report_path


def test_delete_report_rejects_unsafe_id():
    # _SAFE_REPORT_ID 拒绝含路径分隔符的非法 id（防目录穿越）
    assert delete_report("../etc/passwd", {"sub": "a@b.com"}, auth_required=False) is False


def test_delete_report_denied_without_access(monkeypatch):
    import app.services.slice_report as sr

    monkeypatch.setattr(sr, "can_access_report", lambda *a, **k: False)
    assert (
        delete_report("slice_general_20260826_111552", {"sub": "a@b.com"}, auth_required=False)
        is False
    )


def test_delete_report_removes_files(tmp_path, monkeypatch):
    import app.services.slice_report as sr

    monkeypatch.setattr(sr, "REPORTS_DIR", tmp_path)
    rid = "slice_general_20260826_111552"
    (tmp_path / f"{rid}.pdf").write_bytes(b"%PDF")
    (tmp_path / f"{rid}.meta.json").write_text("{}")
    (tmp_path / f"{rid}.context.json").write_text("{}")
    assert get_report_path(rid) is not None

    ok = delete_report(rid, {"sub": "a@b.com"}, auth_required=False)
    assert ok is True
    assert get_report_path(rid) is None
    assert not (tmp_path / f"{rid}.meta.json").exists()
    assert not (tmp_path / f"{rid}.context.json").exists()


def test_delete_report_nonexistent_returns_false(tmp_path, monkeypatch):
    import app.services.slice_report as sr

    monkeypatch.setattr(sr, "REPORTS_DIR", tmp_path)
    assert (
        delete_report("slice_general_20260826_111552", {"sub": "a@b.com"}, auth_required=False)
        is False
    )
