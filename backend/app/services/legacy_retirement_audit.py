"""Pre-retirement audit for the legacy dialogue and chapter compatibility path."""
from __future__ import annotations

from pathlib import Path
import re


LEGACY_MARKERS: dict[str, dict[str, str]] = {
    "_FUNC_PATTERNS": {
        "category": "legacy_router",
        "description": "regex function routing patterns",
    },
    "_DIM_PATTERNS": {
        "category": "legacy_router",
        "description": "regex dimension routing patterns",
    },
    "_normalize_act": {
        "category": "legacy_router",
        "description": "post-hoc dialog act normalization",
    },
    "_SOFT_FABRICATE_KW": {
        "category": "legacy_router",
        "description": "soft-fallback fabrication keywords",
    },
    "_SOFT_OOD_KW": {
        "category": "legacy_router",
        "description": "soft-fallback out-of-domain keywords",
    },
    "CUSTOM_CHAPTERS": {
        "category": "chapter_compat",
        "description": "legacy chapter tuple alias",
    },
    "CUSTOM_CHAPTER_DIMENSIONS": {
        "category": "chapter_compat",
        "description": "legacy chapter dimension alias",
    },
    "FUNCTION_RADAR_DIMENSIONS": {
        "category": "chapter_compat",
        "description": "legacy radar chapter mapping",
    },
    "route_chat": {
        "category": "legacy_entrypoint",
        "description": "legacy dialogue entrypoint",
    },
}

_LEGACY_IMPORT_RE = re.compile(
    r"(?m)^\s*(?P<import>(?:from\s+legacy(?:\s|\.)[^\n]*|import\s+legacy(?:\s|\.)[^\n]*))"
)


def audit_legacy_retirement(
    root: str | Path,
    *,
    shadow_gate_passed: bool = False,
) -> dict:
    root_path = Path(root)
    markers = {
        name: {
            "category": metadata["category"],
            "description": metadata["description"],
            "count": 0,
            "files": [],
        }
        for name, metadata in LEGACY_MARKERS.items()
    }
    legacy_imports: list[dict[str, str]] = []

    for path in root_path.rglob("*.py"):
        if path.name == "legacy_retirement_audit.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        import_match = _LEGACY_IMPORT_RE.search(text)
        if import_match:
            legacy_imports.append(
                {
                    "file": str(path.relative_to(root_path)),
                    "import": import_match.group("import").strip(),
                }
            )
        for name, entry in markers.items():
            count = text.count(name)
            if count:
                entry["count"] += count
                entry["files"].append(str(path.relative_to(root_path)))

    remaining = {
        name: entry
        for name, entry in markers.items()
        if entry["count"] > 0
    }
    blockers: list[str] = []
    if not shadow_gate_passed:
        blockers.append("shadow_gate_not_passed")
    if legacy_imports:
        blockers.append("active_app_imports_legacy")
    if remaining:
        blockers.append("legacy_markers_remain")
    if any(entry["category"] == "legacy_entrypoint" for entry in remaining.values()):
        blockers.append("legacy_entrypoint_still_active")
    if any(entry["category"] == "chapter_compat" for entry in remaining.values()):
        blockers.append("chapter_compatibility_still_imported")

    return {
        "safe_to_retire": not blockers,
        "shadow_gate_passed": shadow_gate_passed,
        "markers": markers,
        "legacy_imports": legacy_imports,
        "remaining_markers": sorted(remaining),
        "blockers": blockers,
        "required_order": [
            "pass shadow evaluation gate",
            "remove all active-app imports of the legacy package",
            "replace legacy entrypoint with semantic primary",
            "remove unreferenced compatibility aliases",
            "delete legacy regex fallback only after regression suite is green",
            "update redline and rollback documentation",
        ],
    }
