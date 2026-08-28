"""Chat 路由语义层集成：LLM 优先解析路径 + 无 LLM 降级不再回退 'hint' 死胡同。"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def _run_blocking(fn, *args, **kwargs):
    return fn(*args, **kwargs)


def _patch_common(monkeypatch):
    monkeypatch.setattr("app.services.session_store.ensure_session_id", lambda sid=None: "s1")
    monkeypatch.setattr("app.services.session_store.get_session", lambda sid=None: {})
    monkeypatch.setattr("app.services.session_store.store_session", lambda *a, **k: None)
    monkeypatch.setattr("app.services.conclusion_store.save_conclusion", lambda **k: "c1")
    monkeypatch.setattr("app.services.conclusion_store.covered_functions", lambda sid, dimension=None: set())
    from app.services import chat_router

    monkeypatch.setattr(chat_router, "run_blocking", _run_blocking)


@pytest.mark.asyncio
async def test_route_chat_llm_path_returns_query_type(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services.intent_engine import IntentResult
    from app.services import chat_router

    _patch_common(monkeypatch)
    monkeypatch.setattr(
        "app.services.intent_engine.recognize",
        lambda q, session_context=None: IntentResult(function="general", dimension="overall", intent="general"),
    )
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    async def fake_parse(query, session_context=None, *, dictionary=None):
        return SemanticQuery(query_type="ranking", metrics=["credit_score"], dimensions=["industry_l1"])

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        return [], [], {}

    async def fake_reply(query, claims, followups, *, report_hint=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.llm_semantic_parser.parse_semantic_query", fake_parse)
    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "信用分前10的行业", session_id="s1")
    assert out["query_type"] == "ranking"
    assert out["data"]["query_type"] == "ranking"
    assert out["function"] == "score"


@pytest.mark.asyncio
async def test_route_chat_no_llm_trend_not_hint(monkeypatch):
    from app.schemas.claim import Claim, ClaimTrace, ClaimValue
    from app.services import chat_router

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: False)

    trend_claim = Claim(
        claim="制造行业营收同比均值 3.5%（样本 10）。",
        value=ClaimValue(metric="avg_revenue_yoy", number=3.5, unit="%"),
        trace=ClaimTrace(table="core_metrics", field="revenue_yoy", query_id="Q_trend"),
        confidence="computed",
    )

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        return [trend_claim], [], {}

    async def fake_reply(query, claims, followups, *, report_hint=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "分析各行业的趋势走向", session_id="s1")
    assert out["query_type"] == "trend"
    metrics = [c.get("value", {}).get("metric") for c in out["data"]["claims"]]
    assert "hint" not in metrics
    assert "avg_revenue_yoy" in metrics


@pytest.mark.asyncio
async def test_route_chat_no_llm_comparison(monkeypatch):
    from app.schemas.semantic_query import QueryType
    from app.services import chat_router

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: False)

    captured: dict = {}

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        captured["sq"] = sq
        return [], [], {}

    async def fake_reply(query, claims, followups, *, report_hint=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "江西和湖南制造业信用分对比", session_id="s1")
    # 无 LLM 时「A 和 B 对比」不再退回 aggregation，而是规则层产出 comparison
    assert captured["sq"].query_type == QueryType.comparison
    assert captured["sq"].compare[0].values == ["江西", "湖南"]
    assert out["query_type"] == "comparison"
    assert out["function"] == "benchmark"


@pytest.mark.asyncio
async def test_route_chat_report_question_routes_to_faq_not_report(monkeypatch):
    from app.schemas.semantic_query import QueryType
    from app.services.intent_engine import IntentResult
    from app.services import chat_router

    _patch_common(monkeypatch)
    # 规则层会把「报告怎么生成」判成 report —— 正是要防的劫持
    monkeypatch.setattr(
        "app.services.intent_engine.recognize",
        lambda q, session_context=None: IntentResult(function="report", dimension="overall", intent="report_overall"),
    )
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: False)

    captured: dict = {}

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        captured["sq"] = sq
        return [], [], {}

    async def fake_reply(query, claims, followups, *, report_hint=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "报告怎么生成", session_id="s1")
    # 走 FAQ 语义路径，而非报告意图（report 意图会走 run_judgment + 切片报告，而不是 run_semantic_query）
    assert captured["sq"].query_type == QueryType.faq
    assert out["query_type"] == "faq"
    assert out["function"] == "general"


def test_no_llm_fallback_semantic_layer_not_hint():
    from app.services import semantic_query
    from app.services.intent_engine import recognize

    sq = semantic_query.intent_to_semantic_query(recognize("分析各行业的趋势走向"))
    assert sq.query_type == "trend"
    assert sq.metrics == ["revenue_yoy"]
    assert semantic_query.query_type_to_function(sq) == "trend"

    g = semantic_query.intent_to_semantic_query(recognize("你好"))
    assert g.query_type == "aggregation"
    assert semantic_query.query_type_to_function(g) == "score"
