"""Executable legacy-retirement audit for the current repository state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.legacy_retirement_audit import audit_legacy_retirement


def _default_app_root() -> Path:
    return Path(__file__).resolve().parents[1] / "app"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=_default_app_root())
    parser.add_argument("--shadow-gate-passed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = audit_legacy_retirement(
        args.root,
        shadow_gate_passed=args.shadow_gate_passed,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"safe_to_retire={report['safe_to_retire']}")
        print(f"blockers={','.join(report['blockers']) or 'none'}")
        print(f"remaining_markers={','.join(report['remaining_markers']) or 'none'}")

    raise SystemExit(0 if report["safe_to_retire"] else 1)


if __name__ == "__main__":
    main()
