from __future__ import annotations

from pathlib import Path

from app.services.legacy_retirement_audit import audit_legacy_retirement


def test_audit_detects_legacy_route_and_chapter_markers(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "dialog.py").write_text(
        "_FUNC_PATTERNS = []\n_DIM_PATTERNS = []\n_normalize_act = None\n",
        encoding="utf-8",
    )
    (app / "templates.py").write_text(
        "CUSTOM_CHAPTERS = {}\nCUSTOM_CHAPTER_DIMENSIONS = {}\n",
        encoding="utf-8",
    )
    (app / "router.py").write_text(
        "from app.services.chat_router import route_chat\n",
        encoding="utf-8",
    )

    report = audit_legacy_retirement(tmp_path, shadow_gate_passed=False)
    assert report["safe_to_retire"] is False
    assert report["markers"]["_FUNC_PATTERNS"]["count"] == 1
    assert report["markers"]["CUSTOM_CHAPTERS"]["count"] == 1
    assert report["markers"]["route_chat"]["count"] == 1
    assert "shadow_gate_not_passed" in report["blockers"]
    assert "legacy_markers_remain" in report["blockers"]


def test_audit_can_pass_when_gate_passed_and_modules_are_clean(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "clean.py").write_text("VALUE = 1\n", encoding="utf-8")
    report = audit_legacy_retirement(tmp_path, shadow_gate_passed=True)
    assert report["safe_to_retire"] is True
    assert report["blockers"] == []


def test_audit_excludes_its_own_scanner_source(tmp_path: Path):
    services = tmp_path / "app" / "services"
    services.mkdir(parents=True)
    (services / "legacy_retirement_audit.py").write_text(
        "LEGACY_MARKERS = {'route_chat': {}, 'CUSTOM_CHAPTERS': {}}\n",
        encoding="utf-8",
    )
    report = audit_legacy_retirement(tmp_path, shadow_gate_passed=True)
    assert report["safe_to_retire"] is True
    assert all(entry["count"] == 0 for entry in report["markers"].values())