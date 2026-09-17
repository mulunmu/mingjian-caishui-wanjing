"""Safely delete LangGraph threads older than the configured retention window."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from app.db.urls import get_sync_engine


def _existing_tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def cleanup_old_threads(
    engine,
    *,
    older_than_days: int = 7,
    dry_run: bool = True,
    keep_threads: list[str] | None = None,
) -> dict:
    if older_than_days < 1:
        raise ValueError("older_than_days must be >= 1")
    tables = _existing_tables(engine)
    if "checkpoints" not in tables:
        return {"ok": True, "skipped": "checkpoints table missing", "threads": []}

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    keep = set(keep_threads or [])
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT thread_id, MAX((checkpoint->>'ts')::timestamptz) AS last_ts "
                "FROM checkpoints GROUP BY thread_id "
                "HAVING MAX((checkpoint->>'ts')::timestamptz) < :cutoff "
                "ORDER BY last_ts"
            ),
            {"cutoff": cutoff},
        ).all()
        old_threads = [str(row.thread_id) for row in rows if str(row.thread_id) not in keep]
        last_seen = {
            str(row.thread_id): row.last_ts.isoformat() if row.last_ts else None
            for row in rows
            if str(row.thread_id) not in keep
        }
        if not old_threads or dry_run:
            return {
                "ok": True,
                "dry_run": dry_run,
                "cutoff": cutoff.isoformat(),
                "thread_count": len(old_threads),
                "threads": old_threads,
                "last_seen": last_seen,
            }

        deleted: dict[str, int] = {}
        for table in ("checkpoint_blobs", "checkpoint_writes", "checkpoints"):
            if table not in tables:
                continue
            result = session.execute(
                text(f"DELETE FROM {table} WHERE thread_id IN :thread_ids").bindparams(
                    bindparam("thread_ids", expanding=True)
                ),
                {"thread_ids": old_threads},
            )
            deleted[table] = int(result.rowcount or 0)
        session.commit()
    return {
        "ok": True,
        "dry_run": False,
        "cutoff": cutoff.isoformat(),
        "thread_count": len(old_threads),
        "threads": old_threads,
        "last_seen": last_seen,
        "deleted": deleted,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--apply", action="store_true", help="actually delete rows")
    parser.add_argument("--keep-thread", action="append", default=[])
    args = parser.parse_args()
    report = cleanup_old_threads(
        get_sync_engine(),
        older_than_days=args.days,
        dry_run=not args.apply,
        keep_threads=args.keep_thread,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
