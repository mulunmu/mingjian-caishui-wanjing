from __future__ import annotations

import pytest

from app.schemas.semantic_frame import SemanticFrame
from app.services.composition_catalog import build_composition_catalog
from app.services.composition_validator import validate_composition_plan
from app.services.dialogue_composition import build_dialogue_composition_plan


def test_single_intent_plan_uses_typed_intent_policy_content_and_synthesis():
    frame = SemanticFrame(
        policy_route="analysis",
        business_domain="warn",
        task_type="comparison",
        metrics=["debt_ratio"],
    )
    plan = build_dialogue_composition_plan(query="对比资产负债率", frame=frame)
    assert plan is not None
    assert plan.metadata["intent_module_ids"] == ["intent_analysis"]
    assert plan.metadata["policy_module_ids"] == ["policy_analysis"]
    assert plan.metadata["content_module_ids"] == ["content_comparison"]
    assert validate_composition_plan(plan, build_composition_catalog()).valid


def test_multi_intent_plan_has_one_validated_path_per_segment():
    plan = build_dialogue_composition_plan(
        query="进一步看真实性交叉验证；按地区拆分趋势；生成报告",
    )
    assert plan is not None
    assert plan.metadata["multi_intent"] is True
    assert len(plan.metadata["segments"]) == 3
    assert len(plan.metadata["intent_module_ids"]) == 3
    assert plan.output_node_ids == ["synthesis"]
    assert validate_composition_plan(plan, build_composition_catalog()).valid


def test_topic_reference_uses_memory_intent_and_content_modules():
    frame = SemanticFrame(policy_route="analysis", task_type="metric_lookup")
    plan = build_dialogue_composition_plan(query="回到上上个问题继续分析", frame=frame)
    assert plan is not None
    assert plan.metadata["intent_module_ids"] == ["intent_memory"]
    assert plan.metadata["content_module_ids"] == ["content_memory"]
    assert validate_composition_plan(plan, build_composition_catalog()).valid


@pytest.mark.parametrize(
    ("route", "expected_intent"),
    [
        ("analysis", "intent_analysis"),
        ("report", "intent_report"),
        ("capability", "intent_knowledge"),
        ("product_faq", "intent_knowledge"),
        ("greeting", "intent_social"),
        ("feedback", "intent_social"),
        ("abuse", "intent_social"),
        ("language_switch", "intent_social"),
        ("clarify", "intent_clarify"),
        ("refuse", "intent_refusal"),
        ("out_of_domain", "intent_refusal"),
        ("unknown_entity", "intent_clarify"),
    ],
)
def test_every_policy_route_has_a_valid_dialogue_composition(route, expected_intent):
    frame = SemanticFrame(policy_route=route, task_type="policy")
    plan = build_dialogue_composition_plan(query="测试", frame=frame)
    assert plan is not None
    assert plan.metadata["intent_module_ids"] == [expected_intent]
    assert validate_composition_plan(plan, build_composition_catalog()).valid
