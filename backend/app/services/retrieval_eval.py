"""Pure retrieval metrics used by Stage 18 audits."""
from __future__ import annotations

from typing import Any


def score_retrieval(expected_tool_id: str, ranked_ids: list[str]) -> dict[str, float]:
    rank = ranked_ids.index(expected_tool_id) + 1 if expected_tool_id in ranked_ids else 0
    return {
        "recall_at_1": 1.0 if rank == 1 else 0.0,
        "recall_at_5": 1.0 if 0 < rank <= 5 else 0.0,
        "precision_at_5": (1.0 / max(1, len(ranked_ids[:5]))) if 0 < rank <= 5 else 0.0,
        "mrr": (1.0 / rank) if rank else 0.0,
    }


def aggregate_retrieval_metrics(
    scores: list[dict[str, float]],
    *,
    min_recall_at_5: float = 0.9,
) -> dict[str, Any]:
    total = len(scores)
    if not total:
        return {"ok": False, "total": 0, "recall_at_1": 0.0, "recall_at_5": 0.0, "precision_at_5": 0.0, "mrr": 0.0}
    averaged = {
        key: round(sum(float(item.get(key, 0.0)) for item in scores) / total, 6)
        for key in ("recall_at_1", "recall_at_5", "precision_at_5", "mrr")
    }
    return {"ok": averaged["recall_at_5"] >= min_recall_at_5, "total": total, **averaged}
