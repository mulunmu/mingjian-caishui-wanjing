"""Build semantic frames from the coarse policy route and query."""
from __future__ import annotations

import re

from app.schemas.conversation_route import ConversationRoute
from app.schemas.semantic_frame import SemanticFrame


_REFERENCE_RE = re.compile(r"上一个|上上个|上上上|回到.*问题|刚才|之前")

_EXTRA_METRIC_ALIASES = {
    "debt_ratio": ("资产负债率",),
    "cash_flow_net": ("现金流", "现金流净额", "现金净额"),
    "current_ratio": ("流动比率",),
    "gross_margin": ("毛利率",),
    "net_margin": ("净利率",),
    "roe": ("净资产收益率", "ROE"),
    "tax_arrears_cnt": ("欠税",),
    "red_invoice_cnt": ("红字发票", "红冲"),
}


def _extract_metrics(query: str) -> list[str]:
    from app.services.metric_registry import CANONICAL_METRICS

    text = (query or "").lower()
    matched: list[str] = []
    for metric in CANONICAL_METRICS:
        key = metric["metric_key"]
        name = metric.get("name") or ""
        if key.lower() in text or (name and name in text):
            matched.append(key)
            continue
        if any(alias.lower() in text for alias in _EXTRA_METRIC_ALIASES.get(key, ())):
            matched.append(key)
    for key, aliases in _EXTRA_METRIC_ALIASES.items():
        if key not in matched and any(alias.lower() in text for alias in aliases):
            matched.append(key)
    return list(dict.fromkeys(matched))


def frame_from_route(
    route: ConversationRoute,
    *,
    query: str,
    metrics: list[str] | None = None,
) -> SemanticFrame:
    detected_metrics = list(metrics or _extract_metrics(query))
    if route.route == "analysis" and len(detected_metrics) > 1:
        task_type = "multi_metric"
    elif route.route in {"analysis", "language_switch"}:
        task_type = "metric_lookup"
    elif route.route == "report":
        task_type = "report"
    elif route.route == "product_faq":
        task_type = "knowledge"
    elif route.route == "unknown_entity":
        task_type = "clarify"
    else:
        task_type = "policy"

    references = ["topic_reference"] if _REFERENCE_RE.search(query or "") else []
    if route.entities:
        subject_scope = "individual"
    elif references:
        subject_scope = "unbound"
    elif route.route in {"capability", "product_faq", "greeting", "feedback", "abuse"}:
        subject_scope = "system"
    elif route.route in {"analysis", "report"}:
        subject_scope = "cohort"
    else:
        subject_scope = "unbound"

    missing_slots: list[str] = []
    if route.needs_clarification:
        missing_slots.append("required_slots")

    output_requirements = ["reply"]
    if route.route in {"analysis", "report"}:
        output_requirements.append("claims")
    if route.route == "report":
        output_requirements.append("report")

    return SemanticFrame(
        policy_route=route.route,
        speech_act="social" if route.route in {"greeting", "feedback", "abuse"} else (
            "refusal" if route.route == "refuse" else "question"
        ),
        business_domain=route.domain or "general",
        task_type=task_type,
        subject_scope=subject_scope,
        entities=list(route.entities),
        metrics=detected_metrics,
        output_requirements=output_requirements,
        references=references,
        language=route.language,
        safety=route.safety,
        missing_slots=missing_slots,
        confidence=float(route.confidence),
    )
