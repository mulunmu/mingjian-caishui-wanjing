from __future__ import annotations

from app.services.tool_rag import RagTool, ToolSnapshot
from app.services.tool_embedding_index import plan_embedding_changes


def _tool(tool_id: str, title: str) -> RagTool:
    return RagTool(
        tool_id=tool_id,
        kind="atomic_metric",
        title=title,
        description=f"{title}描述",
        aliases=(title,),
        examples=(),
        required_params=(),
        dependencies=(),
        chapter_links=(),
        scenarios=(),
        shape="single_value",
    )


def test_embedding_plan_skips_unchanged_and_removes_unsupported():
    snapshot = ToolSnapshot(tools=(_tool("metric_a", "指标A"), _tool("metric_b", "指标B")))
    from app.services.embedding_service import content_hash

    existing_hash_a = content_hash(snapshot.tools[0].retrieval_text)
    plan = plan_embedding_changes(
        snapshot,
        existing={snapshot.tools[0].tool_id: existing_hash_a, "metric_removed": "old"},
        model_name="test-model",
    )

    assert plan.unchanged == ("metric_a",)
    assert plan.added == ("metric_b",)
    assert plan.updated == ()
    assert plan.removed == ("metric_removed",)


def test_embedding_plan_detects_changed_document():
    original = ToolSnapshot(tools=(_tool("metric_a", "指标A"),))
    changed = ToolSnapshot(tools=(_tool("metric_a", "指标A新版"),))
    from app.services.embedding_service import content_hash

    plan = plan_embedding_changes(
        changed,
        existing={"metric_a": content_hash(original.tools[0].retrieval_text)},
        model_name="test-model",
    )
    assert plan.updated == ("metric_a",)
