from __future__ import annotations

import pytest

from app.services.dialog_act import DialogAct, classify
from app.services.shadow_integration import dialog_act_to_raw_route


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    ["我能问哪些指标？", "能同时分析多个指标吗？"],
)
async def test_metric_capability_questions_are_deterministic(query, monkeypatch):
    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "llm_available", lambda: True)
    act = await classify(query, {})

    assert act.act == "negotiate_scope"
    assert act.ask_kind == "overview"


def test_abuse_variants_are_routed_to_deescalation():
    for query in ("这破系统真垃圾", "你是不是废物", "滚，别分析了", "真蠢，答非所问"):
        route = dialog_act_to_raw_route(DialogAct(act="meta_session", confidence=0.9), query)
        assert route["route"] == "abuse", query


def test_supported_english_request_routes_to_language_switch():
    for query in ("Can you analyze financial risk?", "Show me a cash flow analysis."):
        route = dialog_act_to_raw_route(DialogAct(act="meta_session", confidence=0.9), query)
        assert route["route"] == "language_switch", query


def test_unknown_entity_and_underspecified_variants_do_not_abstain():
    unknown = dialog_act_to_raw_route(
        DialogAct(act="meta_session", confidence=0.9),
        "看看不存在公司的现金流",
    )
    unclear = dialog_act_to_raw_route(
        DialogAct(act="meta_session", confidence=0.9),
        "这个怎么样",
    )

    assert unknown["route"] == "unknown_entity"
    assert unclear["route"] == "clarify"


def test_new_canonical_tools_are_retrievable_and_executable():
    from app.services.semantic_registry_seed import seed_semantic_registry
    from app.services.semantic_tool_executors import semantic_executor_tool_ids
    from app.services.tool_rag import ToolRagRetriever, load_tool_snapshot_sync
    from tests.test_semantic_registry_seed import _engine

    engine = _engine()
    seed_semantic_registry(engine)
    retriever = ToolRagRetriever(
        load_tool_snapshot_sync(engine),
        semantic_executor_tool_ids(),
    )

    assert "metric_industry_score" in semantic_executor_tool_ids()
    assert "metric_industry_score" in {
        item.tool_id for item in retriever.retrieve("和同行比处在什么位置", top_k=5)
    }
    assert "metric_fraud_composite_score" in {
        item.tool_id for item in retriever.retrieve("哪里值得优先核查", top_k=5)
    }
    assert retriever.retrieve(
        "分析各行业的趋势走向",
        top_k=5,
        executable_only=True,
    )[0].tool_id == "metric_revenue_yoy"
