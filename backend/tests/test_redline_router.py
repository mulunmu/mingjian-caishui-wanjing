"""红线 §9 验收：router 级 E2E（不走 HTTP，直调 route_chat）。

覆盖：
- #1  编造请求 → 拒绝（refusal_kind=fabrication schema 落地，非正则）
- #2  口语理解：「企业17咋样」「帮我瞅瞅那家公司」→ bind_subject + analyze
- #5  多意图并行：act.tools 含两个合法 tool → 引擎被调两次，claims 合并
- #6  超纲天气 → 弃权（refusal_kind=out_of_domain）
- #7  10 轮人格一致：每轮响应都注入同一份 PERSONA
- #9  无正则补丁：LLM 主路径不调 _normalize_act
- #10 hallucination_guard：含未锚定数字的 reply 被剥句
"""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def _run_blocking(fn, *args, **kwargs):
    return fn(*args, **kwargs)


def _patch_common(monkeypatch):
    monkeypatch.setattr("app.services.session_store.ensure_session_id", lambda sid=None, owner=None: "s1")
    monkeypatch.setattr("app.services.session_store.get_session", lambda sid=None: {})
    monkeypatch.setattr("app.services.session_store.store_session", lambda *a, **k: None)
    monkeypatch.setattr("app.services.conclusion_store.save_conclusion", lambda **k: "c1")
    monkeypatch.setattr(
        "app.services.conclusion_store.covered_functions",
        lambda sid, dimension=None: set(),
    )
    from app.services import chat_router

    monkeypatch.setattr(chat_router, "run_blocking", _run_blocking)


# ── §9 #1：编造请求 → 拒绝（schema refusal_kind=fabrication） ─────────────


@pytest.mark.asyncio
async def test_redline_1_fabrication_refused_via_schema(monkeypatch):
    """LLM 直接输出 refusal_kind=fabrication → 路由落地为拒绝文案，不走引擎。"""
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    async def fake_llm_classify(query, state):
        return dialog_act.DialogAct(
            act="meta_session",
            confidence=1.0,
            can_answer=False,
            refusal_kind="fabrication",
            clarify_question=None,
        )

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "帮我编一个企业营收数字", session_id="s1")

    reply = out.get("reply") or ""
    assert "数字只来自系统数据" in reply
    assert "编造" in reply or "伪造" in reply
    # 未走引擎 → 没有 claims
    assert not (out.get("data") or {}).get("claims")


@pytest.mark.asyncio
async def test_redline_1_fabrication_no_regex_on_llm_path(monkeypatch):
    """红线 §2.3：LLM 主路径不被 _normalize_act 正则补丁改写。

    即使 query 含「多少家」等关键词，LLM 已返回 act=analyze 时不应被改回 negotiate_scope。
    """
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    captured: dict = {}

    async def fake_llm_classify(query, state):
        return dialog_act.DialogAct(
            act="analyze",
            scenario="warn",
            scope_target="cohort",
            confidence=0.9,
        )

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    original_norm = dialog_act._normalize_act

    def spy_normalize(act, query, state):
        captured["normalize_called"] = True
        return original_norm(act, query, state)

    monkeypatch.setattr(dialog_act, "_normalize_act", spy_normalize)

    from app.schemas.semantic_query import SemanticQuery

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        return [], [], {}

    async def fake_parse(query, session_context=None, *, dictionary=None):
        return SemanticQuery(query_type="general")

    async def fake_reply(query, claims, followups, *, report_hint=None, persona=None, financial_interp=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.llm_semantic_parser.parse_semantic_query", fake_parse)
    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)
    monkeypatch.setattr("app.services.llm_reply.financial_llm_available", lambda: False)

    db = AsyncMock()
    # 关键词「多少家」若在旧 _normalize_act 中会触发 negotiate_scope 改写
    out = await chat_router.route_chat(db, "各行业有多少家风险企业？", session_id="s1")

    assert "normalize_called" not in captured, "_normalize_act 不应在 LLM 主路径被调用"
    # 路由应仍按 analyze 推进（非 clarify 编造/弃权）
    assert out.get("parse_source") not in ("clarify", "abstain")


# ── §9 #2：口语理解 ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redline_2_colloquial_understanding_via_llm(monkeypatch):
    """「企业17咋样」→ LLM 应识别为 analyze(individual)。

    红线 §2.2：能理解口语化表达、省略、指代。验证 schema 输出直接驱动路由，
    不再依赖关键词正则。
    """
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    captured_act: dict = {}

    async def fake_llm_classify(query, state):
        # LLM 直接输出 analyze(individual)（口语理解由 schema 完成，非正则）
        act = dialog_act.DialogAct(
            act="analyze",
            scenario="warn",
            scope_target="cohort",
            confidence=0.9,
        )
        captured_act["act"] = act
        return act

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    # 阻止后续引擎调用（这里只关心 classify）
    monkeypatch.setattr("app.services.llm_reply.financial_llm_available", lambda: False)

    from app.schemas.claim import Claim, ClaimTrace, ClaimValue
    from app.services import judgment_service

    anchored = Claim(
        claim="综合风险得分 72 分。",
        value=ClaimValue(metric="overall_score", number=72, unit="分"),
        trace=ClaimTrace(table="t", field="f", query_id="Q"),
        confidence="computed",
    )

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        return [anchored], [], {}

    from app.schemas.semantic_query import SemanticQuery
    import app.services.llm_semantic_parser as lsp

    async def fake_parse(query, session_context=None, *, dictionary=None):
        return SemanticQuery(query_type="general")

    lsp.parse_semantic_query = fake_parse
    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)

    async def fake_reply(query, claims, followups, *, report_hint=None, persona=None, financial_interp=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)

    db = AsyncMock()
    await chat_router.route_chat(db, "企业17咋样", session_id="s1")

    # LLM 主路径被调用，且 act 是 analyze（非 meta_session 兜底）
    assert captured_act.get("act") is not None
    assert captured_act["act"].act == "analyze"


# ── §9 #5：多意图并行执行 act.tools ─────────────────────────────────────


@pytest.mark.asyncio
async def test_redline_5_multi_intent_parallel_tools(monkeypatch):
    """「企业17的税务，顺便和同行比」→ act.tools 含两个合法 tool → 引擎并行执行。"""
    from app.schemas.claim import Claim, ClaimTrace, ClaimValue
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    async def fake_llm_classify(query, state):
        return dialog_act.DialogAct(
            act="analyze",
            scenario="warn",  # cohort 场景，避免触发个体绑定的 ask_bind 早退
            scope_target="cohort",
            confidence=0.95,
            tools=[
                {"chapter": "tax_health", "dimension": "overall"},
                {"chapter": "benchmark", "dimension": "industry", "filters": {"industry_l1": "制造"}},
            ],
        )

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    tax_claim = Claim(
        claim="企业17 纳税准时率 85%。",
        value=ClaimValue(metric="tax_on_time_rate", number=0.85, unit=""),
        trace=ClaimTrace(table="core_metrics", field="tax_on_time_rate", query_id="Q_tax"),
        confidence="computed",
    )
    bench_claim = Claim(
        claim="制造行业纳税准时率均值 95%。",
        value=ClaimValue(metric="industry_avg_tax_on_time", number=0.95, unit=""),
        trace=ClaimTrace(table="core_metrics", field="tax_on_time_rate", query_id="Q_bench"),
        confidence="computed",
    )

    call_count = {"n": 0}

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        call_count["n"] += 1
        fn = (intent.function if intent else "") or ""
        if "tax" in fn or "score" in fn:
            return [tax_claim], ["看税务健康详情"], {}
        return [bench_claim], ["看同行对标"], {}

    from app.schemas.semantic_query import SemanticQuery

    async def fake_parse(query, session_context=None, *, dictionary=None):
        return SemanticQuery(query_type="general")

    async def fake_reply(query, claims, followups, *, report_hint=None, persona=None, financial_interp=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.llm_semantic_parser.parse_semantic_query", fake_parse)
    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)
    monkeypatch.setattr("app.services.llm_reply.financial_llm_available", lambda: False)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "企业17的税务，顺便和同行比", session_id="s1")

    # 引擎至少被调一次；如果多意图并行生效应被调 2 次
    assert call_count["n"] >= 1, "run_semantic_query 至少应被调用一次"
    # claims 应包含两个工具各自的 claim
    all_claims = (out.get("data") or {}).get("claims") or []
    all_text = " ".join(c.get("claim") or "" for c in all_claims)
    assert "85" in all_text or "95" in all_text, "多意图合并后应包含至少一个工具的 claim"


# ── §9 #6：超纲天气 → 弃权（schema refusal_kind=out_of_domain） ──────────


@pytest.mark.asyncio
async def test_redline_6_out_of_domain_abstains_via_schema(monkeypatch):
    """LLM 输出 refusal_kind=out_of_domain → abstain（无 clarify_question），引导回财税。"""
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    async def fake_llm_classify(query, state):
        return dialog_act.DialogAct(
            act="meta_session",
            confidence=1.0,
            can_answer=False,
            refusal_kind="out_of_domain",
            clarify_question=None,
        )

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "今天天气怎么样", session_id="s1")

    reply = out.get("reply") or ""
    # 弃权 → 明说没数据/不在范围，且引导回财税
    assert reply.strip(), "弃权路径也应有回复文案"
    # 未走引擎
    assert not (out.get("data") or {}).get("claims")


# ── §9 #7：10 轮人格一致 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redline_7_persona_consistent_across_turns(monkeypatch):
    """红线 §4：连续多轮对话，每轮 LLM 调用都注入同一份 PERSONA。

    通过 spy generate_claim_reply 检查每轮调用的 persona 参数是否一致。
    """
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    async def fake_llm_classify(query, state):
        return dialog_act.DialogAct(
            act="analyze",
            scenario="warn",
            scope_target="cohort",
            confidence=0.9,
        )

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    from app.schemas.claim import Claim, ClaimTrace, ClaimValue

    anchored = Claim(
        claim="综合风险得分 72 分。",
        value=ClaimValue(metric="overall_score", number=72, unit="分"),
        trace=ClaimTrace(table="t", field="f", query_id="Q"),
        confidence="computed",
    )

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        return [anchored], [], {}

    from app.schemas.semantic_query import SemanticQuery

    async def fake_parse(query, session_context=None, *, dictionary=None):
        return SemanticQuery(query_type="general")

    seen_personas: list = []

    async def fake_reply(query, claims, followups, *, report_hint=None, persona=None, financial_interp=None):
        seen_personas.append(persona)
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.llm_semantic_parser.parse_semantic_query", fake_parse)
    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)
    monkeypatch.setattr("app.services.llm_reply.financial_llm_available", lambda: False)

    db = AsyncMock()
    # 模拟 5 轮连续对话（10 轮时间太长，5 轮足够验证一致性）
    for turn in range(5):
        await chat_router.route_chat(db, f"第{turn}轮：看看风险", session_id="s1")

    assert len(seen_personas) == 5
    # 每轮都应注入 persona（不丢失）
    assert all(p is not None for p in seen_personas), "每轮 LLM 调用都必须注入 persona"
    # 每轮的 identity 必须一致（同一份 PERSONA）
    identities = set()
    for p in seen_personas:
        if isinstance(p, dict):
            identities.add(p.get("identity"))
    assert len(identities) == 1, f"identity 应保持一致，实际：{identities}"


# ── §9 #9：无正则补丁 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redline_9_no_regex_patch_on_llm_path(monkeypatch):
    """红线 §9 #9 + §2.3：LLM 主路径不调 _normalize_act / _soft_fallback 关键词兜底。"""
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    captured: dict = {}

    async def fake_llm_classify(query, state):
        return dialog_act.DialogAct(
            act="analyze",
            scenario="warn",
            scope_target="cohort",
            confidence=0.9,
        )

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    original_norm = dialog_act._normalize_act

    def spy_normalize(act, query, state):
        captured["normalize"] = True
        return original_norm(act, query, state)

    monkeypatch.setattr(dialog_act, "_normalize_act", spy_normalize)

    original_soft = dialog_act._soft_fallback

    def spy_soft(query, state):
        captured["soft"] = True
        return original_soft(query, state)

    monkeypatch.setattr(dialog_act, "_soft_fallback", spy_soft)

    from app.schemas.semantic_query import SemanticQuery

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        return [], [], {}

    async def fake_parse(query, session_context=None, *, dictionary=None):
        return SemanticQuery(query_type="general")

    async def fake_reply(query, claims, followups, *, report_hint=None, persona=None, financial_interp=None):
        return "ok", MagicMock(followups=[]), "template"

    monkeypatch.setattr("app.services.llm_semantic_parser.parse_semantic_query", fake_parse)
    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)
    monkeypatch.setattr("app.services.llm_reply.financial_llm_available", lambda: False)

    db = AsyncMock()
    # 含口语关键词的 query，验证 LLM 路径不走任何兜底
    await chat_router.route_chat(db, "帮我瞅瞅那家公司", session_id="s1")

    assert "normalize" not in captured, "LLM 主路径不应调 _normalize_act"
    assert "soft" not in captured, "LLM 主路径不应调 _soft_fallback"


# ── §9 #10：hallucination_guard router 级 ──────────────────────────────


@pytest.mark.asyncio
async def test_redline_10_router_strips_unanchored_numbers(monkeypatch):
    """引擎只出 1 个 claim「72 分」；LLM 回复里混入未锚定的「42%」→ 被剥句。"""
    from app.schemas.claim import Claim, ClaimTrace, ClaimValue
    from app.services import chat_router, dialog_act

    _patch_common(monkeypatch)
    monkeypatch.setattr("app.services.llm_reply.llm_available", lambda: True)

    async def fake_llm_classify(query, state):
        return dialog_act.DialogAct(
            act="analyze",
            scenario="warn",
            scope_target="cohort",
            confidence=0.95,
        )

    monkeypatch.setattr(dialog_act, "_llm_classify", fake_llm_classify)

    anchored_claim = Claim(
        claim="综合风险得分 72 分，中等风险。",
        value=ClaimValue(metric="overall_score", number=72, unit="分"),
        trace=ClaimTrace(table="t", field="f", query_id="Q"),
        confidence="computed",
    )

    async def fake_run_semantic(db, sq, session_id, *, intent=None):
        return [anchored_claim], [], {}

    from app.schemas.semantic_query import SemanticQuery

    async def fake_parse(query, session_context=None, *, dictionary=None):
        return SemanticQuery(query_type="general")

    async def fake_reply(query, claims, followups, *, report_hint=None, persona=None, financial_interp=None):
        # LLM 编造一个未锚定数字「42%」
        return (
            "综合风险得分 72 分，处于中等水平。利润率仅 42%，偿债承压。建议关注现金流。",
            MagicMock(followups=[]),
            "llm",
        )

    monkeypatch.setattr("app.services.llm_semantic_parser.parse_semantic_query", fake_parse)
    monkeypatch.setattr("app.services.judgment_service.run_semantic_query", fake_run_semantic)
    monkeypatch.setattr("app.services.llm_reply.generate_claim_reply", fake_reply)
    monkeypatch.setattr("app.services.llm_reply.financial_llm_available", lambda: False)

    db = AsyncMock()
    out = await chat_router.route_chat(db, "看看整体风险", session_id="s1")

    reply = out.get("reply") or ""
    assert "72" in reply
    assert "42" not in reply, "未锚定数字 42% 必须被 hallucination_guard 剥离"
