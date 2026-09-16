"""Deterministic normalization for model-produced conversation routes."""
from __future__ import annotations

import re

from app.schemas.conversation_route import ConversationRoute


_EXPLICIT_ENTITY_PATTERNS = (
    re.compile(r"企业\s*(\d+)", re.IGNORECASE),
    re.compile(r"\bENT(\d+)\b", re.IGNORECASE),
    re.compile(r"\bcompany\s+(\d+)\b", re.IGNORECASE),
)
_NAMED_COMPANY_RE = re.compile(r"([\u4e00-\u9fffA-Za-z0-9]{2,20})这家公司")
_REPORT_REQUEST_RE = re.compile(r"(请|帮我)?\s*(生成|导出|定制).{0,12}报告")
_AGGREGATE_TERMS = ("各行业", "全库", "整体", "全样本", "所有企业")


def _extract_explicit_entities(query: str, existing: list[str]) -> list[str]:
    out = [item for item in existing if item]
    for match in _EXPLICIT_ENTITY_PATTERNS[0].finditer(query):
        out.append(f"企业{match.group(1)}")
    for match in _EXPLICIT_ENTITY_PATTERNS[1].finditer(query):
        out.append(f"ENT{match.group(1)}")
    for match in _EXPLICIT_ENTITY_PATTERNS[2].finditer(query):
        out.append(f"company {match.group(1)}")
    for match in _NAMED_COMPANY_RE.finditer(query):
        out.append(match.group(1))
    return list(dict.fromkeys(out))


def normalize_route(raw: dict, query: str) -> ConversationRoute:
    allowed_routes = ConversationRoute.model_fields["route"].annotation.__args__
    route_name = raw.get("route") or "clarify"
    if route_name not in allowed_routes:
        route_name = "clarify"

    domain = raw.get("domain")
    if domain not in {"loan", "rating", "warn", "audit", "report", "general", None}:
        domain = None
    language = raw.get("language") or "zh"
    entities = _extract_explicit_entities(query, list(raw.get("entities") or []))
    needs_clarification = bool(raw.get("needs_clarification"))

    if _REPORT_REQUEST_RE.search(query):
        route_name = "report"
        domain = "report"
        needs_clarification = False
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
        needs_tools=bool(raw.get("needs_tools")),
        needs_clarification=needs_clarification,
        confidence=float(raw.get("confidence") or 0.5),
    )
