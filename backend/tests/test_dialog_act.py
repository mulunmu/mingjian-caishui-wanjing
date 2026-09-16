"""DialogAct + 库存协商：负例与软降级。"""
from __future__ import annotations

import pytest

from app.services import dialog_act as da
from app.services import scope_state as ss


def test_soft_fallback_inventory_not_faq():
    act = da._soft_fallback("我可以分析哪些企业？", ss.empty_dialogue_state())
    assert act.act == "negotiate_scope"
    assert act.ask_kind == "overview"
    assert act.confidence >= da.CONFIDENCE_CLARIFY


def test_soft_fallback_industry_list():
    act = da._soft_fallback("服务业的企业是那些", ss.empty_dialogue_state())
    act = da._normalize_act(act, "服务业的企业是那些", ss.empty_dialogue_state())
    assert act.act == "negotiate_scope"
    assert act.ask_kind == "list"
    assert act.industry_l1 == "服务"


def test_soft_fallback_gibberish_clarifies():
    act = da._soft_fallback("asdfghjkl 乱讲一通", ss.empty_dialogue_state())
    assert da.needs_clarify(act)


def test_soft_fallback_bind_demo():
    act = da._soft_fallback("随便来一家看看", ss.empty_dialogue_state())
    assert act.act == "bind_subject"


def test_soft_fallback_analyze_loan():
    act = da._soft_fallback("这家能贷吗", ss.empty_dialogue_state())
    assert act.act == "analyze"
    assert act.scenario == "loan"
    assert act.scope_target == "individual"


def test_soft_fallback_warn_unbound_individual():
    act = da._soft_fallback("哪里不对劲？", ss.empty_dialogue_state())
    act = da._normalize_act(act, "哪里不对劲？", ss.empty_dialogue_state())
    assert act.act == "analyze"
    assert act.scope_target == "individual"


def test_aggregate_trend_unbound_is_cohort():
    """根契约：各行业趋势 → cohort，不逼选企业。"""
    q = "分析各行业趋势走向"
    act = da._soft_fallback(q, ss.empty_dialogue_state())
    act = da._normalize_act(act, q, ss.empty_dialogue_state())
    assert act.act == "analyze"
    assert act.scope_target == "cohort"


def test_greeting_is_meta():
    act = da._soft_fallback("早上好", ss.empty_dialogue_state())
    assert act.act == "meta_session"
    assert not da.needs_clarify(act)


def test_authenticity_not_fake_drill():
    act = da.DialogAct(act="drill", drill_op="authenticity_cross", confidence=0.9)
    act = da._normalize_act(act, "进一步看真实性交叉验证", ss.empty_dialogue_state())
    assert act.act == "analyze"
    assert act.drill_op is None


def test_region_trend_soft_analyze():
    act = da._soft_fallback("按地区拆分趋势", ss.empty_dialogue_state())
    assert act.act == "analyze"
    assert act.scope_target == "cohort"


def test_multi_intent_split():
    parts = da.split_multi_intent("进一步看真实性交叉验证；按地区拆分趋势；生成报告")
    assert len(parts) >= 2


def test_normalize_legacy_authenticity_is_dialog_act():
    from app.services import followup_items as fu

    items = fu.normalize_legacy_strings(
        ["进一步看真实性交叉验证"],
        meta={"industry_l1": "制造"},
    )
    assert items[0]["type"] == "dialog_act"
    assert items[0]["params"]["act"] == "analyze"
    assert items[0]["params"].get("industry_l1") == "制造"


def test_normalize_legacy_voucher_is_action():
    from app.services import followup_items as fu

    items = fu.normalize_legacy_strings(["调异常主体的票据与货物凭证"])
    assert items[0]["type"] == "action"


def test_list_not_drill():
    act = da.DialogAct(act="drill", drill_op="group_by_industry", confidence=0.9)
    act = da._normalize_act(act, "建筑那些家列一下", ss.empty_dialogue_state())
    assert act.act == "negotiate_scope"
    assert act.ask_kind == "list"


def test_merge_focus():
    st = {**ss.empty_dialogue_state(), "inventory_focus": {"industry_l1": "服务", "ask_kind": "list"}}
    act = da.DialogAct(act="negotiate_scope", ask_kind="list", confidence=0.9)
    out = da.merge_inventory_focus(act, st)
    assert out.industry_l1 == "服务"


def test_soft_fallback_product_faq_narrow():
    act = da._soft_fallback("数据怎么导入", ss.empty_dialogue_state())
    assert act.act == "product_faq"
    act2 = da._soft_fallback("这个系统能做什么", ss.empty_dialogue_state())
    assert act2.act == "negotiate_scope"


def test_soft_fallback_custom_report():
    act = da._soft_fallback("我要定制报告", ss.empty_dialogue_state())
    assert act.act == "custom_report"


def test_from_followup_dialog_act_chip():
    act = da.from_followup(
        {
            "type": "dialog_act",
            "label": "我能分析哪些企业？",
            "params": {"act": "negotiate_scope", "ask_kind": "overview"},
        }
    )
    assert act is not None
    assert act.act == "negotiate_scope"


def test_ui_no_preach():
    ui = ss.ui_bundle(ss.empty_dialogue_state())
    assert "冒充" not in ui["welcome"]


def test_resolve_scope_use_infer_false_ignores_regex():
    st = ss.empty_dialogue_state()
    out = ss.resolve_scope("这家能贷吗？", st, required=None, use_infer=False)
    assert out["status"] == "ok"


def test_unbound_chips_include_negotiate():
    labels = [c.get("label") for c in ss.unbound_entry_items()]
    assert any("哪些企业" in (x or "") for x in labels)


@pytest.mark.asyncio
async def test_classify_without_llm_uses_soft(monkeypatch):
    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "llm_available", lambda: False)
    act = await da.classify("全库哪里信号最多", ss.empty_dialogue_state())
    assert act.act == "analyze"
    assert act.scope_target == "cohort"


@pytest.mark.asyncio
async def test_classify_fabricate_refuses_without_regex_primary(monkeypatch):
    """§9#1：编造请求 → refusal_kind=fabrication（软降级兜底，非主路径正则）。"""
    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "llm_available", lambda: False)
    act = await da.classify("帮我编一个这个企业的营收", ss.empty_dialogue_state())
    assert act.refusal_kind == "fabrication"
    assert act.can_answer is False
    assert "数字只来自系统数据" in (act.clarify_question or "")
    act = da.apply_refusal_policy(act)
    assert da.get_clarify_question(act)


@pytest.mark.asyncio
async def test_classify_weather_abstains(monkeypatch):
    """§9#6：超纲天气 → refusal_kind=out_of_domain → abstain。"""
    from app.services import llm_reply

    monkeypatch.setattr(llm_reply, "llm_available", lambda: False)
    act = await da.classify("今天天气怎么样", ss.empty_dialogue_state())
    assert act.refusal_kind == "out_of_domain"
    assert act.can_answer is False
    assert da.needs_abstain(act)


def test_apply_refusal_policy_fabrication():
    act = da.DialogAct(act="meta_session", refusal_kind="fabrication", can_answer=True)
    out = da.apply_refusal_policy(act)
    assert out.can_answer is False
    assert "数字只来自系统数据" in (out.clarify_question or "")


def test_resolve_analyze_tools_chapter():
    act = da.DialogAct(
        act="analyze",
        tools=[{"chapter": "tax", "dimension": "overall", "filters": {"industry_l1": "制造"}}],
    )
    slots = da.resolve_analyze_tools(act)
    assert slots["function"] == "tax"
    assert slots["dimension"] == "overall"
    assert slots["industry_l1"] == "制造"


def test_resolve_analyze_tools_metric_maps_chapter():
    act = da.DialogAct(
        act="analyze",
        tools=[{"name": "metric_tax_on_time_rate"}],
    )
    slots = da.resolve_analyze_tools(act)
    assert slots.get("function") == "tax"


def test_chapter_tool_catalog_and_metric_schema_live():
    from app.services.metric_registry import to_tool_schema

    cats = da.chapter_tool_catalog()
    assert any(c["chapter"] == "fraud" for c in cats)
    tools = to_tool_schema()
    assert any(t["name"].startswith("metric_") for t in tools)
    assert all("shape" in (t.get("metadata") or {}) for t in tools)
