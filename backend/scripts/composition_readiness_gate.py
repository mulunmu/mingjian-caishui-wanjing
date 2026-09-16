"""Print composition persistence and execution readiness."""
from __future__ import annotations

import json

from app.db.urls import get_sync_engine
from app.services.composition_readiness import build_composition_readiness_report


def main() -> None:
    report = build_composition_readiness_report(get_sync_engine())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
