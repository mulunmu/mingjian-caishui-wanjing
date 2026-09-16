from __future__ import annotations

from pathlib import Path

from app.services.legacy_retirement_audit import audit_legacy_retirement


def test_audit_detects_legacy_route_and_chapter_markers(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "dialog.py").write_text(
        "_FUNC_PATTERNS = []\n_DIM_PATTERNS = []\nnormalize_fallback_act = None\n",
        encoding="utf-8",
    )
    (app / "templates.py").write_text(
        "CUSTOM_CHAPTERS = {}\nCUSTOM_CHAPTER_DIMENSIONS = {}\n",
        encoding="utf-8",
    )
    (app / "router.py").write_text(
        "from legacy.chat_router import route_chat\n",
        encoding="utf-8",
    )

    report = audit_legacy_retirement(tmp_path, shadow_gate_passed=False)
    assert report["safe_to_retire"] is False
    assert report["markers"]["_FUNC_PATTERNS"]["count"] == 1
    assert report["markers"]["CUSTOM_CHAPTERS"]["count"] == 1
    assert report["markers"]["route_chat"]["count"] == 1
    assert report["legacy_imports"][0]["file"] == "app/router.py"
    assert "shadow_gate_not_passed" in report["blockers"]
    assert "legacy_markers_remain" in report["blockers"]
    assert "active_app_imports_legacy" in report["blockers"]


def test_audit_can_pass_when_gate_passed_and_modules_are_clean(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "clean.py").write_text("VALUE = 1\n", encoding="utf-8")
    report = audit_legacy_retirement(tmp_path, shadow_gate_passed=True)
    assert report["safe_to_retire"] is True
    assert report["blockers"] == []
    assert report["legacy_imports"] == []
    assert report["legacy_package_present"] is False


def test_audit_blocks_when_archived_legacy_package_still_exists(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "clean.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "legacy").mkdir()

    report = audit_legacy_retirement(app, shadow_gate_passed=True)

    assert report["safe_to_retire"] is False
    assert report["legacy_package_present"] is True
    assert report["blockers"] == ["legacy_package_still_present"]


def test_audit_blocks_any_active_app_legacy_import_without_known_markers(tmp_path: Path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "bridge.py").write_text(
        "from legacy.archived_bridge import helper\n",
        encoding="utf-8",
    )

    report = audit_legacy_retirement(tmp_path, shadow_gate_passed=True)

    assert report["safe_to_retire"] is False
    assert report["legacy_imports"] == [
        {"file": "app/bridge.py", "import": "from legacy.archived_bridge import helper"}
    ]
    assert report["blockers"] == ["active_app_imports_legacy"]


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


def test_current_app_is_retired_from_legacy_imports_and_markers():
    app_root = Path(__file__).resolve().parents[1] / "app"
    report = audit_legacy_retirement(app_root, shadow_gate_passed=True)

    for marker in report["markers"]:
        assert report["markers"][marker]["count"] == 0
    assert report["legacy_imports"] == []
    assert report["legacy_package_present"] is False
    assert report["remaining_markers"] == []
    assert report["blockers"] == []
    assert report["safe_to_retire"] is True
