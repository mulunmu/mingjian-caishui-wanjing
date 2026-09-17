"""Evaluate dense + BM25 + fusion retrieval on the golden query set."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

from sqlalchemy import func, select

from app.db.session import get_async_session_factory
from app.models.semantic_embedding import SemanticEmbedding
from app.services.embedding_service import FastEmbedProvider, embedding_model_name
from app.services.hybrid_tool_rag import retrieve_tools_hybrid
from app.services.retrieval_eval import aggregate_retrieval_metrics, score_retrieval
from app.services.retrieval_golden_set import GOLDEN_QUERIES
from app.services.semantic_tool_executors import semantic_executor_tool_ids
from app.services.tool_rag import load_tool_snapshot


async def run() -> dict:
    os.environ.setdefault("RAG_HYBRID_ENABLED", "true")
    factory = get_async_session_factory()
    async with factory() as db:
        snapshot = await load_tool_snapshot(db)
        embedding_count = int(
            await db.scalar(
                select(func.count())
                .select_from(SemanticEmbedding)
                .where(SemanticEmbedding.model_name == embedding_model_name())
            )
            or 0
        )
        provider = FastEmbedProvider()
        provider.embed_query("预热")
        executable_ids = semantic_executor_tool_ids()
        results: list[dict] = []
        leakage: list[dict] = []
        dense_hits = 0
        latencies: list[float] = []
        for query, expected in GOLDEN_QUERIES:
            started = time.perf_counter()
            candidates = await retrieve_tools_hybrid(
                db,
                query,
                snapshot=snapshot,
                top_k=5,
                kinds={"atomic_metric", "composite_metric"},
                executable_only=True,
                embedder=provider,
            )
            latencies.append((time.perf_counter() - started) * 1000)
            ranked = [candidate.tool_id for candidate in candidates]
            if any(candidate.tool_id not in executable_ids for candidate in candidates):
                leakage.append({"query": query, "ranked": ranked})
            if any("dense" in candidate.matched_by for candidate in candidates):
                dense_hits += 1
            results.append({"query": query, "expected": expected, "ranked": ranked, **score_retrieval(expected, ranked)})

        aggregate = aggregate_retrieval_metrics(results, min_recall_at_5=0.90)
        dense_coverage = round(dense_hits / max(1, len(results)), 4)
        failures = [item for item in results if item["recall_at_5"] == 0.0]
        ok = (
            aggregate["ok"]
            and not leakage
            and embedding_count >= len(snapshot.tools)
            and dense_coverage >= 0.90
        )
        ordered_latency = sorted(latencies)
        p50 = ordered_latency[int(round((len(ordered_latency) - 1) * 0.50))] if ordered_latency else 0.0
        p95 = ordered_latency[int(round((len(ordered_latency) - 1) * 0.95))] if ordered_latency else 0.0
        return {
            "ok": ok,
            "model_name": embedding_model_name(),
            "validated_tools": len(snapshot.tools),
            "embedded_tools": embedding_count,
            "dense_coverage": dense_coverage,
            "latency_ms": {"p50": round(p50, 3), "p95": round(p95, 3), "max": round(max(latencies), 3) if latencies else 0.0},
            "unsupported_leakage": leakage,
            "metrics": aggregate,
            "failures": failures,
            "results": results,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"ok={report['ok']} recall@1={report['metrics']['recall_at_1']} "
            f"recall@5={report['metrics']['recall_at_5']} mrr={report['metrics']['mrr']} "
            f"dense_coverage={report['dense_coverage']}"
        )
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
