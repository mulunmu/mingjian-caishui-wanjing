"""Print the combined readiness and shadow release decision."""
from __future__ import annotations

import argparse
import json

from app.db.urls import get_sync_engine
from app.services.deployment_gate import build_deployment_gate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-samples", type=int, default=20)
    args = parser.parse_args()
    report = build_deployment_gate(
        get_sync_engine(),
        min_shadow_samples=args.min_samples,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()