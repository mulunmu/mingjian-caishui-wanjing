"""AI 主导的定制报告对话：意图识别 + 状态机 + 章节自由组合（不碰固定报告回归）。"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.schemas.custom_report import CustomReportSpec
from app.services import custom_report as cr
from app.services.intent_engine import recognize
from app.services.report_templates import (
    CUSTOM_CHAPTERS,
    get_scenario_label,
    get_scenario_tone,
)


# ── 意图：定制 vs 固定报告，二者并存不回归 ──

def test_intent_custom_report():
    assert recognize("我要定制报告").function == "custom_report"
    assert recognize("帮我定制一份风控报告").function == "custom_report"
    assert recognize("自定义报告").function == "custom_report"


def test_intent_fixed_report_still_report():
    # 「生成报告」不含定制词，仍命中固定 report 路径（不回归）
    assert recognize("生成报告").function == "report"
    assert recognize("生成财务健康体检报告").function == "report"


# ── 状态机：退出 / 确认词 ──

def test_new_state():
    s = cr.new_state()
    assert s["active"] is True
    assert s["stage"] == "asking"
    assert s["turn"] == 0
    assert s["spec"] is None


def test_is_exit():
    assert cr.is_exit("退出") is True
    assert cr.is_exit("退出定制") is True
    assert cr.is_exit("算了") is True
    assert cr.is_exit("制造业") is False


def test_is_confirm():
    assert cr.is_confirm("确认生成") is True
    assert cr.is_confirm("生成") is True
    assert cr.is_confirm("就按这个") is True
    assert cr.is_confirm("换成固定报告") is False


# ── 槽位 clamp：词表白名单 + 去重（弃权优先，不编造非法章节） ──

def test_normalize_spec_clamps_chapters():
    spec = CustomReportSpec(chapters=["financial", "financial", "nope", "tax"])
    out = cr.normalize_spec(spec)
    assert out is not None
    assert out.chapters == ["financial", "tax"]  # 去重 + 剔除非法 key


def test_normalize_spec_drops_unknown_scope():
    spec = CustomReportSpec(chapters=["financial"], industry_l1="外星行业", province="火星")
    out = cr.normalize_spec(spec)
    assert out is not None
    assert out.industry_l1 is None
    assert out.province is None


def test_normalize_spec_keeps_valid_scope():
    spec = CustomReportSpec(chapters=["tax"], industry_l1="制造", province="广东")
    out = cr.normalize_spec(spec)
    assert out is not None
    assert out.industry_l1 == "制造"
    assert out.province == "广东"


# ── 章节自由组合：转成引擎可消费的 spec dict ──

def test_spec_to_report_spec_order_and_dimensions():
    spec = CustomReportSpec(
        chapters=["fraud", "financial", "signal"],
        industry_l1="制造",
        province="广东",
        title="我的定制报告",
        purpose="排查发票异常",
    )
    r = cr.spec_to_report_spec(spec)
    assert r["title"] == "我的定制报告"
    assert [ch["function"] for ch in r["chapters"]] == ["fraud", "financial", "signal"]
    # dimension 取各自默认（对齐固定场景既有用法）
    assert r["chapters"][0]["dimension"] == "industry"  # fraud
    assert r["chapters"][1]["dimension"] == "overall"  # financial
    assert r["chapters"][2]["dimension"] == "signal"  # signal
    # 每个章节都有平实标题/说明，供 LLM 用户可见
    assert all(ch["title"] for ch in r["chapters"])


def test_proposal_text_lists_chapters():
    spec = CustomReportSpec(chapters=["financial", "tax"], title="定制风控报告")
    text = cr.proposal_text(spec)
    assert "定制风控报告" in text
    assert "财务健康" in text
    assert "税务合规" in text
    assert "确认生成" in text


# ── 无 LLM 降级：规则把诉求映射到固定场景，弃权优先 ──

def test_rule_turn_maps_scenario():
    result = cr.rule_turn({"purpose": "财务健康"}, "")
    assert result["stage"] == "propose"
    assert result["llm"] is False
    spec = result["spec"]
    assert spec is not None
    assert spec.chapters  # financial 场景的章节子集


def test_rule_turn_unknown_scenario_abstains():
    result = cr.rule_turn({"purpose": ""}, "")
    assert result["stage"] == "asking"
    assert result["spec"] is None


# ── 场景语气/标签：custom 不再落到「综合尽调」 ──

def test_custom_scenario_label_and_tone():
    assert get_scenario_label("custom") == "定制风控报告（对话式自由组合）"
    assert get_scenario_tone("custom")["persona"] == "风控定制顾问"


# ── 数据驱动槽位累计 + 弃权兜底（最大化覆盖，不死磕） ──

def test_match_chapters_maps_keywords_in_mention_order():
    assert cr.match_chapters("财务健康和发票舞弊") == ["financial", "fraud"]
    assert cr.match_chapters("趋势") == ["trend"]
    assert cr.match_chapters("随便聊聊") == []


def test_infer_title():
    assert cr.infer_title(["financial"]) == "财务健康风险报告"
    assert cr.infer_title(["financial", "fraud"]) == "财务健康与发票舞弊风险报告"
    assert cr.infer_title([]) == "定制风控报告"


def test_accumulate_slots_builds_spec_from_data():
    state = cr.new_state()
    state["purpose"] = "制造也的趋势"
    cr.accumulate_slots(state)
    assert state["spec"]["chapters"] == ["trend"]
    assert state["spec"]["industry_l1"] == "制造"

    state["purpose"] = "制造也的趋势 内部经营分析 广东 财务健康"
    cr.accumulate_slots(state)
    spec = cr._spec_from_slots(state)
    assert spec is not None
    assert "trend" in spec.chapters and "financial" in spec.chapters
    assert spec.province == "广东"
    assert spec.industry_l1 == "制造"


def test_salvage_proposes_when_slots_recognized():
    state = cr.new_state()
    state["turn"] = cr.MAX_TURNS + 1  # 模拟轮次耗尽
    state["purpose"] = "制造也的趋势 内部经营分析 广东 财务健康"
    cr.accumulate_slots(state)
    result = cr._salvage_or_give_up(state)
    assert result["stage"] == "propose"
    assert result["spec"] is not None
    assert "财务健康" in result["reply"] and "营收趋势" in result["reply"]


def test_salvage_gives_up_when_nothing_recognized():
    state = cr.new_state()
    state["turn"] = cr.MAX_TURNS + 1
    state["purpose"] = "你好 今天天气不错"
    cr.accumulate_slots(state)
    result = cr._salvage_or_give_up(state)
    assert result["stage"] == "asking"
    assert result["spec"] is None


@pytest.mark.asyncio
async def test_next_turn_salvages_on_turn_cap_without_llm():
    state = cr.new_state()
    state["turn"] = cr.MAX_TURNS  # 下一轮会 > MAX_TURNS，触发弃权兜底
    state["purpose"] = "制造也的趋势 财务健康 广东"
    result = await cr.next_turn(state, "财务健康")
    assert result["stage"] == "propose"
    assert result["spec"] is not None
    assert result["spec"].chapters  # trend + financial 均被覆盖
    assert "trend" in result["spec"].chapters
