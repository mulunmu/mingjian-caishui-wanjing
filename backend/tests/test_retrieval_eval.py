from __future__ import annotations

from app.services.retrieval_eval import aggregate_retrieval_metrics, score_retrieval


def test_retrieval_metrics_rank_and_mrr():
    score = score_retrieval("metric_b", ["metric_a", "metric_b", "metric_c"])
    assert score["recall_at_1"] == 0.0
    assert score["recall_at_5"] == 1.0
    assert score["mrr"] == 0.5


def test_aggregate_retrieval_metrics_requires_recall_gate():
    aggregate = aggregate_retrieval_metrics(
        [
            {"recall_at_1": 0.0, "recall_at_5": 1.0, "precision_at_5": 0.2, "mrr": 0.5},
            {"recall_at_1": 1.0, "recall_at_5": 1.0, "precision_at_5": 0.2, "mrr": 1.0},
        ],
        min_recall_at_5=0.9,
    )
    assert aggregate["recall_at_5"] == 1.0
    assert aggregate["ok"] is True
