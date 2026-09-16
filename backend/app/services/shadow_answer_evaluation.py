"""Observation and readiness checks for semantic answer composition in shadow mode."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models.shadow_answer_evaluation import ShadowAnswerObservationRecord
from app.schemas.shadow_answer_evaluation import ShadowAnswerObservation
from app.services.route_normalize import normalize_route
from app.services.semantic_answer_composer import compose_semantic_turn


def _digest(query: str) -> str:
    return hashlib.sha256((query or "").encode("utf-8")).hexdigest()


async def evaluate_shadow_answer(
    *,
    db,
    session_id: str,
    query: str,
    raw_route: dict,
    snapshot=None,
    composer=None,
) -> ShadowAnswerObservation:
    started = time.perf_counter()
    route = normalize_route(raw_route, query)
    try:
        fn = composer or compose_semantic_turn
        result = await fn(
            db=db,
            session_id=session_id,
            query=query,
            raw_route=raw_route,
            snapshot=snapshot,
        )
        return ShadowAnswerObservation(
            query_digest=_digest(query),
            session_id=session_id,
            status=result.status,
            route=result.route.route,
            domain=result.route.domain,
            candidate_tool_ids=[item.tool_id for item in result.candidates],
            plan_tool_ids=[step.tool_id for step in (result.plan.steps if result.plan else [])],
            claim_count=len(result.claims),
            reply_present=bool((result.reply or "").strip()),
            latency_ms=(time.perf_counter() - started) * 1000,
        )
    except Exception as exc:
        return ShadowAnswerObservation(
            query_digest=_digest(query),
            session_id=session_id,
            status="error",
            route=route.route,
            domain=route.domain,
            latency_ms=(time.perf_counter() - started) * 1000,
            error=str(exc),
        )


def save_shadow_answer_observation(
    engine: Engine,
    observation: ShadowAnswerObservation,
) -> ShadowAnswerObservationRecord:
    with Session(engine) as session:
        record = ShadowAnswerObservationRecord(
            query_digest=observation.query_digest,
            session_id=observation.session_id,
            status=observation.status,
            route=observation.route,
            domain=observation.domain,
            candidate_tool_ids_json=json.dumps(observation.candidate_tool_ids, ensure_ascii=False),
            plan_tool_ids_json=json.dumps(observation.plan_tool_ids, ensure_ascii=False),
            claim_count=observation.claim_count,
            reply_present=observation.reply_present,
            latency_ms=observation.latency_ms,
            error=observation.error,
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def build_shadow_answer_summary(
    engine: Engine,
    *,
    min_samples: int = 20,
    min_answer_rate: float = 0.60,
    min_reply_present_rate: float = 0.80,
    max_error_rate: float = 0.05,
) -> dict:
    with Session(engine) as session:
        total = int(session.scalar(select(func.count()).select_from(ShadowAnswerObservationRecord)) or 0)
        if total == 0:
            return {
                "ok": False,
                "samples": 0,
                "answer_rate": 0.0,
                "reply_present_rate": 0.0,
                "error_rate": 0.0,
                "avg_claim_count": 0.0,
                "avg_latency_ms": 0.0,
                "failures": ["no_shadow_answer_samples"],
            }
        rows = list(session.scalars(select(ShadowAnswerObservationRecord)))

    answer_rate = sum(1 for row in rows if row.status == "answered") / total
    reply_present_rate = sum(1 for row in rows if row.reply_present) / total
    error_rate = sum(1 for row in rows if row.status == "error") / total
    avg_claim_count = sum(int(row.claim_count or 0) for row in rows) / total
    avg_latency = sum(float(row.latency_ms or 0.0) for row in rows) / total

    failures: list[str] = []
    if total < min_samples:
        failures.append(f"samples_below_min:{total}")
    if answer_rate < min_answer_rate:
        failures.append(f"answer_rate_below_min:{answer_rate:.4f}")
    if reply_present_rate < min_reply_present_rate:
        failures.append(f"reply_present_below_min:{reply_present_rate:.4f}")
    if error_rate > max_error_rate:
        failures.append(f"error_rate_above_max:{error_rate:.4f}")

    return {
        "ok": not failures,
        "samples": total,
        "answer_rate": round(answer_rate, 4),
        "reply_present_rate": round(reply_present_rate, 4),
        "error_rate": round(error_rate, 4),
        "avg_claim_count": round(avg_claim_count, 3),
        "avg_latency_ms": round(avg_latency, 3),
        "failures": failures,
    }