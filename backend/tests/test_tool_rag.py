from __future__ import annotations

from app.services.semantic_registry_seed import seed_semantic_registry
from app.services.tool_rag import ToolRagRetriever, load_tool_snapshot_sync
from tests.test_semantic_registry_seed import _engine


from app.services.retrieval_golden_set import GOLDEN_QUERIES


def test_tool_rag_meets_recall_gate_on_golden_queries():
    engine = _engine()
    seed_semantic_registry(engine)
    retriever = ToolRagRetriever(load_tool_snapshot_sync(engine))
    hits = 0
    misses: list[tuple[str, str, list[str]]] = []
    for query, expected in GOLDEN_QUERIES:
        ids = [candidate.tool_id for candidate in retriever.retrieve(query, top_k=5)]
        if expected in ids:
            hits += 1
        else:
            misses.append((query, expected, ids))
    recall = hits / len(GOLDEN_QUERIES)
    assert recall >= 0.90, misses


def test_planned_tools_are_not_returned():
    engine = _engine()
    seed_semantic_registry(engine)
    retriever = ToolRagRetriever(load_tool_snapshot_sync(engine))
    ids = {
        candidate.tool_id
        for query in ("能不能贷款", "公司稳不稳", "是不是皮包公司", "发票虚开风险")
        for candidate in retriever.retrieve(query, top_k=10)
    }
    assert "scenario_loan_readiness" not in ids
    assert "scenario_business_stability" not in ids
    assert "scenario_shell_company_risk" not in ids
    assert "scenario_invoice_anomaly" not in ids


def test_executable_only_retrieval_filters_unregistered_tools():
    engine = _engine()
    seed_semantic_registry(engine)
    retriever = ToolRagRetriever(load_tool_snapshot_sync(engine))
    ids = [
        candidate.tool_id
        for candidate in retriever.retrieve(
            "现金流稳不稳",
            top_k=10,
            executable_only=True,
        )
    ]
    assert "metric_debt_ratio" in retriever.retrieve(
        "资产负债率高不高",
        top_k=10,
        executable_only=True,
    )[0].tool_id
    assert "metric_cash_flow_level" in ids
    assert "metric_zero_declaration_months" not in retriever.retrieve(
        "长期零申报",
        top_k=10,
        executable_only=True,
    )
