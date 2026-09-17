"""Execute every Stage 17 supported metric against the live PostgreSQL dataset."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import select

from app.db.session import get_async_session_factory
from app.models.core_metrics import CoreMetrics
from app.schemas.semantic_query import QueryType, SemanticQuery
from app.services.extended_metric_executors import build_extended_metric_claims
from app.services.stage17_metric_catalog import SUPPORTED_METRIC_KEYS


async def run() -> dict:
    factory = get_async_session_factory()
    results: list[dict] = []
    async with factory() as db:
        rows = list((await db.execute(select(CoreMetrics).order_by(CoreMetrics.enterprise_id))).scalars().all())
        for metric in sorted(SUPPORTED_METRIC_KEYS):
            sq = SemanticQuery(query_type=QueryType.aggregation, metrics=[metric])
            claims, meta = await build_extended_metric_claims(db, sq, metric, rows)  # type: ignore[misc]
            valid_count = int(meta.get("valid_count") or 0)
            results.append(
                {
                    "metric_key": metric,
                    "valid_count": valid_count,
                    "sample_count": int(meta.get("sample_count") or 0),
                    "sample_claim": claims[0].claim if claims else "",
                    "ok": bool(claims) and valid_count > 0,
                }
            )
    failures = [item for item in results if not item["ok"]]
    return {"ok": not failures, "total": len(results), "passed": len(results) - len(failures), "failures": failures, "results": results}


def main() -> None:
    report = asyncio.run(run())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
