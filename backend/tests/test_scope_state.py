"""范围状态机单元测试（R1–R5 核心）。"""
from app.services import scope_state as ss


def test_query_focus_is_persisted_as_first_class_industry_slot():
    state = ss.merge_analysis_focus(ss.empty_dialogue_state(), industry_l1="制造")
    assert state["industry_focus"] == {"industry_l1": "制造", "province": None}
    assert ss.state_public(state)["industry_focus"]["industry_l1"] == "制造"


def test_detect_query_focus_supports_common_industry_alias():
    assert ss.detect_query_focus("制造业的税务情况")["industry_l1"] == "制造"


def test_multi_industry_focus_preserves_both_industries():
    focus = ss.detect_query_focus("制造业和软件行业的经营真实性对比")
    assert focus["industry_l1_values"][:2] == ["制造", "IT软件"]
    state = ss.merge_query_focus(ss.switch_scope(ss.empty_dialogue_state(), target="cohort"), "制造业和软件行业的经营真实性对比")
    assert state["analysis_focus"]["industry_l1_values"] == ["制造", "IT软件"]


def test_reset_scope_clears_sticky_industry_focus():
    state = ss.merge_query_focus(ss.switch_scope(ss.empty_dialogue_state(), target="cohort"), "制造业的行业地位")
    reset = ss.switch_scope(state, target="unbound")
    assert reset["analysis_focus"] is None


def test_unbound_blocks_individual_query():
    st = ss.empty_dialogue_state()
    out = ss.resolve_scope("这家能贷吗？", st)
    assert out["status"] == "ask_bind"
    assert out["required"] == "individual"


def test_cohort_allows_fraud_without_rebinding():
    st = ss.switch_scope(ss.empty_dialogue_state(), target="cohort")
    out = ss.resolve_scope("哪里可疑要查？", st)
    assert out["status"] == "ok"
    assert out["required"] == "cohort"


def test_cohort_blocks_zhejia():
    st = ss.switch_scope(ss.empty_dialogue_state(), target="cohort")
    out = ss.resolve_scope("这家能贷吗？", st)
    assert out["status"] == "ask_bind"


def test_individual_ok_for_loan():
    st = ss.switch_scope(
        ss.empty_dialogue_state(),
        target="individual",
        subject={"enterprise_id": "E1", "display_name": "企业1"},
    )
    out = ss.resolve_scope("这家能贷吗？", st)
    assert out["status"] == "ok"
    assert out["scenario"] == "loan"


def test_ui_bundle_unbound_has_no_zhejia_chip():
    ui = ss.ui_bundle(ss.empty_dialogue_state())
    labels = [c.get("label") for c in ui["chips"]]
    assert not any("这家能贷吗" in (x or "") for x in labels)
    assert any(c.get("type") == "switch_scope" for c in ui["chips"])


def test_detect_scenario():
    assert ss.detect_scenario("信用怎么样？") == "rating"
    assert ss.detect_scenario("哪里不对劲？") == "warn"
    assert ss.detect_scenario("哪里可疑要查？") == "audit"


def test_focus_history_skip_current_on_recall():
    """§9#4：A→B 后再回溯应回到 A，而不是当前 tip。"""
    st = ss.empty_dialogue_state()
    st = ss.merge_analysis_focus(st, industry_l1="制造")
    st = ss.merge_analysis_focus(st, industry_l1="IT软件")
    assert ss.resolve_focus_from_history(st, "industry") == "制造"
    assert ss.resolve_focus_from_history(st, "industry", skip_current=False) == "IT软件"
