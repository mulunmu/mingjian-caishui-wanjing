from __future__ import annotations

from app.services.hybrid_tool_rag import bm25_rank, fuse_rankings, tokenize_for_bm25
from app.services.tool_rag import RagTool, ToolSnapshot


def _tool(tool_id: str, title: str, aliases: tuple[str, ...]) -> RagTool:
    return RagTool(
        tool_id=tool_id,
        kind="atomic_metric",
        title=title,
        description=f"{title}描述",
        aliases=aliases,
        examples=(),
        required_params=(),
        dependencies=(),
        chapter_links=(),
        scenarios=(),
        shape="single_value",
    )


def test_tokenize_handles_chinese_bigrams_and_ascii_words():
    tokens = tokenize_for_bm25("客户HHI是多少")
    assert "客户" in tokens
    assert "hhi" in tokens


def test_bm25_ranks_alias_match_first():
    snapshot = ToolSnapshot(
        tools=(
            _tool("metric_customer_hhi", "客户HHI", ("客户集中指数",)),
            _tool("metric_cash_flow", "现金流质量", ("经营现金流占比",)),
        )
    )
    ranked = bm25_rank("客户集中指数", snapshot, top_k=2)
    assert ranked[0][0] == "metric_customer_hhi"


def test_rrf_fusion_rewards_consensus_but_keeps_exact_boost():
    ranked, matched = fuse_rankings(
        dense=["metric_a", "metric_b"],
        lexical=["metric_b", "metric_c"],
        rules=["metric_b"],
        weights={"dense": 1.0, "lexical": 1.0, "rules": 1.0},
    )
    assert ranked[0] == "metric_b"
    assert "dense" in matched["metric_b"]
    assert "lexical" in matched["metric_b"]
    assert "exact" in matched["metric_b"]
