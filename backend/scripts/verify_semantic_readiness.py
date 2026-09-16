"""Verify semantic RAG database readiness; --apply runs idempotent setup."""
from __future__ import annotations

import argparse
import json

from app.db.session import Base
from app.db.semantic_migrations import ensure_metric_definition_v2_columns
from app.db.urls import get_sync_engine
from app.services.deployment_readiness import build_semantic_readiness_report
from app.services.semantic_registry_seed import seed_semantic_registry


def apply_semantic_setup(engine) -> dict[str, int]:
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    ensure_metric_definition_v2_columns(engine)
    return seed_semantic_registry(engine)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="apply idempotent schema and seed")
    args = parser.parse_args()
    engine = get_sync_engine()
    applied = apply_semantic_setup(engine) if args.apply else {}
    report = build_semantic_readiness_report(engine)
    if applied:
        report["applied_seed"] = applied
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()