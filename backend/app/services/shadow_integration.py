"""Post-response shadow comparison: legacy path versus semantic candidate path."""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.shadow_evaluation import ShadowEvaluationRecord
from app.schemas.shadow_evaluation import LegacyDialogueSnapshot, ShadowComparison
from app.services.shadow_dialogue import build_shadow_dialogue


_ABUSE_MARKERS = (
    "他妈的",
    "妈的",
    "傻逼",
    "滚蛋",
    "操你",
    "废物系统",
    "垃圾系统",
    "垃圾",
    "废物",
    "真蠢",
    "答非所问",
)

_ABUSE_PATTERNS = (
    re.compile(r"滚(?:吧|蛋|开|远点|[，,!！。]|$)"),
    re.compile(r"破系统|烂系统"),
)

_UNKNOWN_ENTITY_RE = re.compile(
    r"不存在(?:的)?公司|无此企业|虚构企业|测试公司|火星银行|银河集团",
    re.I,
)

_SUPPORTED_ENGLISH_RE = re.compile(
    r"financial|finance|risk|cash\s*flow|metric|report|tax|invoice|loan|credit|analysis|score|email",
    re.I,
)

_UNDERSPECIFIED_RE = re.compile(
    r"^(?:嗯[，, ]*)?(?:继续|分析一下|帮我看看那个|这个怎么样|那个东西有问题吗)"
    r"[。！？!?，, ]*$|"
    r"^[^A-Za-z0-9\u4e00-\u9fff]+(?:哈哈哈|xyz|asdf|乱)?.*$",
    re.I,
)


def _looks_abusive(query: str) -> bool:
    text = query or ""
    return any(marker in text for marker in _ABUSE_MARKERS) or any(
        pattern.search(text) for pattern in _ABUSE_PATTERNS
    )


def _looks_unknown_entity(query: str) -> bool:
    return bool(_UNKNOWN_ENTITY_RE.search(query or ""))


def _looks_underspecified(query: str) -> bool:
    return bool(_UNDERSPECIFIED_RE.match((query or "").strip()))


def _looks_language_switch(query: str) -> bool:
    text = query or ""
    has_latin = bool(re.search(r"[A-Za-z]{3,}", text))
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text))
    return has_latin and not has_cjk


def _digest(query: str) -> str:
    return hashlib.sha256((query or "").encode("utf-8")).hexdigest()


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _domain_from_function(function: str | None) -> str | None:
    mapping = {
        "score": "rating",
        "benchmark": "rating",
        "trend": "rating",
        "authenticity": "audit",
        "fraud": "audit",
        "signal": "warn",
        "tax": "warn",
        "financial": "loan",
        "report": "report",
        "email_report": "report",
    }
    return mapping.get(function or "")


def dialog_act_to_raw_route(act, query: str) -> dict[str, Any]:
    from app.services.dialog_act import looks_greeting

    if not act.can_answer:
        if act.refusal_kind == "fabrication":
            route = "refuse"
        else:
            route = "out_of_domain"
    elif looks_greeting(query):
        route = "greeting"
    elif act.act == "product_faq":
        route = "product_faq"
    elif act.act == "custom_report":
        route = "report"
    elif act.act == "report":
        route = "report"
    elif act.act in {"analyze", "drill"}:
        route = "analysis"
    elif act.act == "bind_subject" or act.confidence < 0.55:
        route = "clarify"
    elif act.act == "negotiate_scope":
        route = "capability"
    else:
        route = "capability"
    if _looks_abusive(query):
        route = "abuse"
    elif _looks_unknown_entity(query):
        route = "unknown_entity"
    elif _looks_language_switch(query) and _SUPPORTED_ENGLISH_RE.search(query or ""):
        route = "language_switch"
    elif _looks_underspecified(query) and route in {"out_of_domain", "refuse", "capability", "clarify"}:
        route = "clarify"
    domain = act.scenario if route in {"analysis", "report"} else None
    return {
        "route": route,
        "domain": domain,
        "language": "zh",
        "entities": [act.subject_ref] if getattr(act, "subject_ref", None) else [],
        "needs_tools": route in {"analysis", "report"},
        "needs_clarification": route == "clarify",
        "confidence": float(act.confidence or 0.5),
    }


def legacy_snapshot_from_result(
    query: str,
    result: dict[str, Any],
) -> LegacyDialogueSnapshot:
    data = result.get("data") or {}
    dialog_act = data.get("dialog_act") or {}
    parse_source = str(result.get("parse_source") or "")
    function = result.get("function")
    query_type = result.get("query_type") or data.get("query_type")
    act = dialog_act.get("act")
    scenario = dialog_act.get("scenario")

    if parse_source == "meta_greeting":
        route = "greeting"
    elif parse_source == "product_faq":
        route = "product_faq"
    elif parse_source == "abstain":
        route = "out_of_domain"
    elif parse_source == "clarify":
        route = "clarify"
    elif parse_source in {"custom_report", "report"} or function in {"report", "email_report"}:
        route = "report"
    elif act == "product_faq":
        route = "product_faq"
    elif act == "custom_report":
        route = "report"
    elif act in {"analyze", "drill"}:
        route = "analysis"
    elif act == "bind_subject":
        route = "clarify"
    elif act == "negotiate_scope":
        route = "capability"
    elif act == "meta_session":
        route = "capability"
    elif function and function not in {"general", "faq"}:
        route = "analysis"
    else:
        route = "capability"

    domain = scenario or _domain_from_function(function)
    if route not in {"analysis", "report", "language_switch"}:
        domain = None
    return LegacyDialogueSnapshot(
        route=route,
        domain=domain,
        function=function,
        query_type=query_type,
        meta={"act": act, "scenario": scenario},
    )


def _raw_route_from_legacy(snapshot: LegacyDialogueSnapshot) -> dict[str, Any]:
    return {
        "route": snapshot.route,
        "domain": snapshot.domain,
        "language": "zh",
        "entities": [],
        "needs_tools": snapshot.route in {"analysis", "report"},
        "needs_clarification": snapshot.route == "clarify",
        "confidence": 0.95,
    }


def expected_tools_for_legacy(snapshot: LegacyDialogueSnapshot) -> list[str]:
    mapping = {
        "score": ["metric_overall_score"],
        "trend": ["metric_revenue_yoy"],
        "authenticity": [
            "metric_authenticity_score",
            "metric_revenue_deviation",
        ],
        "fraud": [
            "metric_red_invoice_cnt",
            "metric_void_invoice_cnt",
            "metric_customer_concentration",
        ],
        "signal": ["chapter_signal"],
        "benchmark": ["chapter_benchmark"],
        "financial": ["metric_debt_ratio", "metric_cash_flow_level"],
        "tax": ["metric_vat_burden", "metric_tax_arrears_cnt"],
        "report": ["chapter_financial"],
        "email_report": ["chapter_financial"],
    }
    return mapping.get(snapshot.function or "", [])


def compare_snapshots(
    *,
    query: str,
    legacy: LegacyDialogueSnapshot,
    shadow_route,
    policy,
    candidate_tool_ids: list[str],
    legacy_latency_ms: float,
    shadow_latency_ms: float,
) -> ShadowComparison:
    expected = expected_tools_for_legacy(legacy)
    if expected:
        coverage = len(set(expected) & set(candidate_tool_ids)) / len(set(expected))
    else:
        coverage = 1.0

    compatible_route = (
        legacy.route == shadow_route.route
        or (
            legacy.route in {"clarify", "capability"}
            and shadow_route.route == "analysis"
            and bool(candidate_tool_ids)
        )
    )
    route_match = compatible_route
    domain_match = (
        legacy.domain == shadow_route.domain
        or legacy.domain is None
        or shadow_route.domain is None
    )
    reasons: list[str] = []
    if not route_match:
        reasons.append(f"route:{legacy.route}->{shadow_route.route}")
    if not domain_match:
        reasons.append(f"domain:{legacy.domain}->{shadow_route.domain}")
    if coverage < 0.5:
        reasons.append(f"tool_coverage:{coverage:.2f}")
    if shadow_latency_ms > max(legacy_latency_ms * 3, 2000):
        reasons.append("shadow_latency_exceeded")
    if legacy.route in {"analysis", "report"} and not candidate_tool_ids:
        reasons.append("no_candidates")

    switch_eligible = (
        route_match
        and domain_match
        and coverage >= 0.5
        and "shadow_latency_exceeded" not in reasons
        and "no_candidates" not in reasons
    )
    return ShadowComparison(
        query_digest=_digest(query),
        legacy_route=legacy.route,
        shadow_route=shadow_route.route,
        legacy_domain=legacy.domain,
        shadow_domain=shadow_route.domain,
        legacy_function=legacy.function,
        legacy_query_type=legacy.query_type,
        candidate_tool_ids=list(candidate_tool_ids),
        expected_tool_ids=expected,
        route_match=route_match,
        domain_match=domain_match,
        tool_coverage=round(coverage, 4),
        legacy_latency_ms=round(float(legacy_latency_ms), 3),
        shadow_latency_ms=round(float(shadow_latency_ms), 3),
        switch_eligible=switch_eligible,
        mismatch_reasons=reasons,
        policy_mode=policy.response_mode,
    )


def run_shadow_evaluation_sync(
    engine: Engine,
    query: str,
    legacy_result: dict[str, Any],
    *,
    session_id: str | None = None,
    legacy_latency_ms: float = 0.0,
    raw_route: dict[str, Any] | None = None,
) -> ShadowComparison:
    legacy = legacy_snapshot_from_result(query, legacy_result)
    started = time.perf_counter()
    with Session(engine) as session:
        shadow = build_shadow_dialogue(
            session,
            query,
            raw_route or _raw_route_from_legacy(legacy),
        )
        shadow_latency_ms = (time.perf_counter() - started) * 1000
        comparison = compare_snapshots(
            query=query,
            legacy=legacy,
            shadow_route=shadow.route,
            policy=shadow.policy,
            candidate_tool_ids=[item.tool_id for item in shadow.candidates],
            legacy_latency_ms=legacy_latency_ms,
            shadow_latency_ms=shadow_latency_ms,
        )
        session.add(
            ShadowEvaluationRecord(
                query_digest=comparison.query_digest,
                session_id=session_id,
                legacy_route=comparison.legacy_route,
                shadow_route=comparison.shadow_route,
                legacy_domain=comparison.legacy_domain,
                shadow_domain=comparison.shadow_domain,
                legacy_function=comparison.legacy_function,
                legacy_query_type=comparison.legacy_query_type,
                candidate_tool_ids_json=_dump(comparison.candidate_tool_ids),
                expected_tool_ids_json=_dump(comparison.expected_tool_ids),
                route_match=comparison.route_match,
                domain_match=comparison.domain_match,
                tool_coverage=comparison.tool_coverage,
                legacy_latency_ms=comparison.legacy_latency_ms,
                shadow_latency_ms=comparison.shadow_latency_ms,
                switch_eligible=comparison.switch_eligible,
                mismatch_reasons_json=_dump(comparison.mismatch_reasons),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    return comparison
