"""Deterministic normalization for model-produced conversation routes."""
from __future__ import annotations

import re

from app.schemas.conversation_route import ConversationRoute
from app.schemas.semantic_action import SemanticAction
from app.services.number_norm import chinese_number_to_int


_EXPLICIT_ENTITY_PATTERNS = (
    re.compile(r"企业\s*(\d+|[零〇一二三四五六七八九十百千万两]+)", re.IGNORECASE),
    re.compile(r"\bENT\s*(\d+|[零〇一二三四五六七八九十百千万两]+)\b", re.IGNORECASE),
    re.compile(r"\bcompany\s+(\d+|[零〇一二三四五六七八九十百千万两]+)\b", re.IGNORECASE),
)
_NAMED_COMPANY_RE = re.compile(r"([\u4e00-\u9fffA-Za-z0-9]{2,20})这家公司")
_AGGREGATE_TERMS = (
    "各行业",
    "全库",
    "整体",
    "全样本",
    "所有企业",
    "哪里信号最多",
    "哪里可疑要查",
    "群体",
    "全库信号",
    "优先核查",
    "按行业",
)
def _extract_explicit_entities(query: str, existing: list[str]) -> list[str]:
    out = [item for item in existing if item]
    for match in _EXPLICIT_ENTITY_PATTERNS[0].finditer(query):
        number = chinese_number_to_int(match.group(1))
        if number is not None:
            out.append(f"企业{number}")
    for match in _EXPLICIT_ENTITY_PATTERNS[1].finditer(query):
        number = chinese_number_to_int(match.group(1))
        if number is not None:
            out.append(f"ENT{number}")
    for match in _EXPLICIT_ENTITY_PATTERNS[2].finditer(query):
        number = chinese_number_to_int(match.group(1))
        if number is not None:
            out.append(f"company {number}")
    for match in _NAMED_COMPANY_RE.finditer(query):
        out.append(match.group(1))
    return list(dict.fromkeys(out))


def normalize_route(raw: dict, query: str) -> ConversationRoute:
    allowed_routes = ConversationRoute.model_fields["route"].annotation.__args__
    route_name = raw.get("route") or "clarify"
    raw_action = raw.get("action")
    action: SemanticAction | None = None
    if raw_action:
        try:
            action = (
                raw_action
                if isinstance(raw_action, SemanticAction)
                else SemanticAction(str(raw_action))
            )
        except ValueError:
            action = None

    action_routes = {
        SemanticAction.ANALYSIS: "analysis",
        SemanticAction.METADATA_QUERY: "inventory",
        SemanticAction.PROFILE: "profile",
        SemanticAction.REPORT: "report",
        SemanticAction.CLARIFY: "clarify",
        SemanticAction.REFUSE: "refuse",
    }
    if action in action_routes:
        route_name = action_routes[action]
    elif action is SemanticAction.CONVERSATION and route_name == "clarify":
        route_name = "capability"
    if route_name not in allowed_routes:
        route_name = "clarify"

    domain = raw.get("domain")
    if domain not in {"loan", "rating", "warn", "audit", "report", "general", None}:
        domain = None
    language = raw.get("language") or "zh"
    entities = _extract_explicit_entities(query, list(raw.get("entities") or []))
    needs_clarification = bool(raw.get("needs_clarification"))

    if action is SemanticAction.REPORT:
        domain = "report"
        needs_clarification = False
    elif action is SemanticAction.ANALYSIS and not domain:
        domain = "general"
    elif route_name in {"analysis", "report"} and language != "zh":
        route_name = "language_switch"

    if entities:
        needs_clarification = False
    elif route_name in {"analysis", "language_switch", "report"}:
        if domain not in {None, "general", "report"} and not any(
            term in query for term in _AGGREGATE_TERMS
        ):
            needs_clarification = True

    return ConversationRoute(
        route=route_name,
        language=language,
        safety=raw.get("safety") or "normal",
        domain=domain,
        entities=entities,
        filters=dict(raw.get("filters") or {}),
        needs_tools=bool(raw.get("needs_tools")),
        needs_clarification=needs_clarification,
        confidence=float(raw.get("confidence") or 0.5),
    )
