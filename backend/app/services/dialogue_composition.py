"""Typed intent, policy and content assembly for dialogue turns."""
from __future__ import annotations

import re
from typing import Any

from app.schemas.composition import (
    CompositionEdge,
    CompositionNode,
    CompositionPlan,
)
from app.services.composition_catalog import build_composition_catalog
from app.services.composition_validator import validate_composition_plan


_INTENT_BY_ROUTE = {
    "analysis": "intent_analysis",
    "report": "intent_report",
    "capability": "intent_knowledge",
    "product_faq": "intent_knowledge",
    "greeting": "intent_social",
    "feedback": "intent_social",
    "abuse": "intent_social",
    "language_switch": "intent_social",
    "clarify": "intent_clarify",
    "refuse": "intent_refusal",
    "out_of_domain": "intent_refusal",
    "unknown_entity": "intent_clarify",
}

_POLICY_BY_INTENT = {
    "intent_analysis": "policy_analysis",
    "intent_memory": "policy_analysis",
    "intent_report": "policy_report",
    "intent_knowledge": "policy_knowledge",
    "intent_social": "policy_social",
    "intent_clarify": "policy_clarify",
    "intent_refusal": "policy_refusal",
}

_CONTENT_BY_TASK = {
    "comparison": "content_comparison",
    "trend": "content_trend",
    "diagnosis": "content_metric_claim",
    "drilldown": "content_metric_claim",
    "multi_metric": "content_metric_claim",
    "metric_lookup": "content_metric_claim",
    "memory": "content_memory",
}

_CONTENT_BY_INTENT = {
    "intent_analysis": "content_metric_claim",
    "intent_memory": "content_memory",
    "intent_report": "content_report",
    "intent_knowledge": "content_knowledge",
    "intent_social": "content_social",
    "intent_clarify": "content_clarify",
    "intent_refusal": "content_refusal",
}

_REFERENCE_RE = re.compile(r"上一个|上上个|上上上|回到.*问题|刚才|之前")
_REPORT_RE = re.compile(r"报告|导出|下载")
_ANALYSIS_RE = re.compile(
    r"分析|风险|指标|评分|负债|现金流|发票|税务|趋势|对比|比较|异常|筛查|真实性"
)
_KNOWLEDGE_RE = re.compile(r"怎么|如何|功能|能力|支持|能不能|是什么|口径|定义")
_SOCIAL_RE = re.compile(r"你好|您好|谢谢|辛苦|再见|嗨|hello|hi", re.I)
_CLARIFY_RE = re.compile(r"具体|补充|哪家|哪个企业|什么意思")


def _intent_from_text(text: str) -> str:
    value = (text or "").strip()
    if _REFERENCE_RE.search(value):
        return "intent_memory"
    if _REPORT_RE.search(value):
        return "intent_report"
    if _SOCIAL_RE.search(value):
        return "intent_social"
    if _ANALYSIS_RE.search(value):
        return "intent_analysis"
    if _KNOWLEDGE_RE.search(value):
        return "intent_knowledge"
    if _CLARIFY_RE.search(value):
        return "intent_clarify"
    return "intent_knowledge"


def _intent_from_route(route: Any) -> str:
    route_value = getattr(route, "policy_route", None) or str(route or "")
    return _INTENT_BY_ROUTE.get(str(route_value), "intent_knowledge")


def _content_for(intent: str, frame: Any | None) -> str:
    task_type = getattr(frame, "task_type", None) if frame is not None else None
    if intent == "intent_analysis" and task_type in _CONTENT_BY_TASK:
        return _CONTENT_BY_TASK[str(task_type)]
    return _CONTENT_BY_INTENT[intent]


def _node(
    node_id: str,
    module_id: str,
    *,
    binding_name: str,
    binding_value: Any,
) -> CompositionNode:
    return CompositionNode(
        node_id=node_id,
        module_id=module_id,
        input_bindings={binding_name: binding_value},
        cost_estimate=0.0,
    )


def build_dialogue_composition_plan(
    *,
    query: str,
    segments: list[str] | None = None,
    intent_hints: list[str] | None = None,
    frame: Any | None = None,
    modules: dict | None = None,
) -> CompositionPlan | None:
    """Build and validate an intent -> policy -> content -> synthesis plan."""
    from app.services.dialog_act import split_multi_intent

    parts = list(segments or [])
    if not parts:
        parts = split_multi_intent(query) or [query]
    parts = [part.strip() for part in parts if part and part.strip()]
    if not parts:
        return None

    hints = list(intent_hints or [])
    intents: list[str] = []
    for index, part in enumerate(parts):
        hint = hints[index] if index < len(hints) else None
        if hint:
            intent = _INTENT_BY_ROUTE.get(str(hint), str(hint))
            if intent not in _POLICY_BY_INTENT:
                intent = _intent_from_text(part)
        elif len(parts) == 1 and frame is not None and not _REFERENCE_RE.search(part):
            intent = _intent_from_route(frame)
        else:
            intent = _intent_from_text(part)
        intents.append(intent)

    nodes: list[CompositionNode] = []
    edges: list[CompositionEdge] = []
    policy_modules: list[str] = []
    content_modules: list[str] = []
    for index, (part, intent) in enumerate(zip(parts, intents, strict=True), 1):
        intent_node = f"intent_{index}"
        policy_node = f"policy_{index}"
        content_node = f"content_{index}"
        policy_module = _POLICY_BY_INTENT[intent]
        content_module = _content_for(intent, frame if len(parts) == 1 else None)
        nodes.extend(
            [
                _node(intent_node, intent, binding_name="query", binding_value=part),
                _node(
                    policy_node,
                    policy_module,
                    binding_name="intent",
                    binding_value=intent,
                ),
                _node(
                    content_node,
                    content_module,
                    binding_name="policy",
                    binding_value=policy_module,
                ),
            ]
        )
        edges.extend(
            [
                CompositionEdge(
                    from_node=intent_node,
                    from_output="intent",
                    to_node=policy_node,
                    to_input="intent",
                ),
                CompositionEdge(
                    from_node=policy_node,
                    from_output="policy",
                    to_node=content_node,
                    to_input="policy",
                ),
                CompositionEdge(
                    from_node=content_node,
                    from_output="fragment",
                    to_node="synthesis",
                    to_input="fragment",
                ),
            ]
        )
        policy_modules.append(policy_module)
        content_modules.append(content_module)

    nodes.append(
        _node(
            "synthesis",
            "content_synthesis",
            binding_name="fragment",
            binding_value=parts,
        )
    )
    plan = CompositionPlan(
        plan_id=f"dialogue-{len(parts)}-{'-'.join(intents)}",
        nodes=nodes,
        edges=edges,
        output_node_ids=["synthesis"],
        metadata={
            "kind": "dialogue",
            "segments": parts,
            "intent_module_ids": intents,
            "policy_module_ids": policy_modules,
            "content_module_ids": content_modules,
            "multi_intent": len(parts) > 1,
        },
    )
    catalog = modules or build_composition_catalog()
    report = validate_composition_plan(plan, catalog)
    return plan if report.valid else None
