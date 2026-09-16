"""Aggregate shadow evaluation records and determine switch readiness."""
from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models.shadow_evaluation import ShadowEvaluationRecord


def build_shadow_evaluation_summary(
    engine: Engine,
    *,
    min_samples: int = 20,
    min_route_match: float = 0.95,
    min_domain_match: float = 0.95,
    min_tool_coverage: float = 0.75,
    min_switch_eligible: float = 0.80,
) -> dict:
    with Session(engine) as session:
        total = int(session.scalar(select(func.count()).select_from(ShadowEvaluationRecord)) or 0)
        if total == 0:
            return {
                "ok": False,
                "samples": 0,
                "route_match_rate": 0.0,
                "domain_match_rate": 0.0,
                "avg_tool_coverage": 0.0,
                "switch_eligible_rate": 0.0,
                "avg_legacy_latency_ms": 0.0,
                "avg_shadow_latency_ms": 0.0,
                "top_mismatch_reasons": [],
                "failures": ["no_shadow_samples"],
            }
        rows = list(session.scalars(select(ShadowEvaluationRecord)))
        route_match_rate = sum(1 for row in rows if row.route_match) / total
        domain_match_rate = sum(1 for row in rows if row.domain_match) / total
        avg_tool_coverage = sum(float(row.tool_coverage or 0.0) for row in rows) / total
        switch_eligible_rate = sum(1 for row in rows if row.switch_eligible) / total
        avg_legacy_latency = sum(float(row.legacy_latency_ms or 0.0) for row in rows) / total
        avg_shadow_latency = sum(float(row.shadow_latency_ms or 0.0) for row in rows) / total
        reasons: Counter[str] = Counter()
        for row in rows:
            try:
                parsed = json.loads(row.mismatch_reasons_json or "[]")
            except (TypeError, ValueError):
                parsed = []
            for reason in parsed:
                reasons[str(reason)] += 1

    failures: list[str] = []
    if total < min_samples:
        failures.append(f"samples_below_min:{total}")
    if route_match_rate < min_route_match:
        failures.append(f"route_match_below_min:{route_match_rate:.4f}")
    if domain_match_rate < min_domain_match:
        failures.append(f"domain_match_below_min:{domain_match_rate:.4f}")
    if avg_tool_coverage < min_tool_coverage:
        failures.append(f"tool_coverage_below_min:{avg_tool_coverage:.4f}")
    if switch_eligible_rate < min_switch_eligible:
        failures.append(f"switch_eligible_below_min:{switch_eligible_rate:.4f}")

    return {
        "ok": not failures,
        "samples": total,
        "route_match_rate": round(route_match_rate, 4),
        "domain_match_rate": round(domain_match_rate, 4),
        "avg_tool_coverage": round(avg_tool_coverage, 4),
        "switch_eligible_rate": round(switch_eligible_rate, 4),
        "avg_legacy_latency_ms": round(avg_legacy_latency, 3),
        "avg_shadow_latency_ms": round(avg_shadow_latency, 3),
        "top_mismatch_reasons": reasons.most_common(10),
        "failures": failures,
    }