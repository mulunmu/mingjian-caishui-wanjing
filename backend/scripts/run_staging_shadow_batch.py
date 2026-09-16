"""Generate real shadow and answer observations against the staging database."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.api.v1.chat import _maybe_run_shadow
from app.db.session import get_async_session_factory
from app.db.urls import get_sync_engine
from app.models.core_metrics import CoreMetrics
from app.services.chat_router import route_chat
from app.services.shadow_answer_evaluation import build_shadow_answer_summary
from app.services.shadow_reporting import build_shadow_evaluation_summary


METRIC_QUERIES = [
    "资产负债率高不高",
    "现金流净额怎么样",
    "增值税税负高不高",
    "欠税多不多",
    "客户是不是太集中",
    "发票数量有多少",
    "红字发票有多少",
    "纳税准时率多少",
]

DIVERSE_METRIC_QUERIES = [
    "流动比率怎么样",
    "毛利率高不高",
    "净利率怎么样",
    "净资产收益率高不高",
    "应收账款周转快不快",
    "所得税税负高不高",
    "滞纳金罚款多不多",
    "作废发票多不多",
]


def build_query_plan(subjects: list[dict], profile: str = "default") -> list[dict]:
    templates = DIVERSE_METRIC_QUERIES if profile == "diverse" else METRIC_QUERIES
    plan: list[dict] = []
    for subject in subjects:
        name = subject.get("name")
        enterprise_id = subject.get("enterprise_id")
        if not name:
            continue
        for query in templates:
            plan.append(
                {
                    "query": f"{name}{query}",
                    "category": "analysis",
                    "enterprise_id": enterprise_id,
                }
            )
    plan.extend(
        [
            {"query": "你好", "category": "greeting"},
            {"query": "你能做什么？", "category": "capability"},
            {"query": "今天天气怎么样？", "category": "out_of_domain"},
            {"query": "帮我编一个企业营收数字", "category": "refusal"},
            {"query": "他妈的这系统怎么用", "category": "abuse"},
            {"query": "Hello, how do I generate a report?", "category": "multilingual"},
        ]
    )
    return plan


async def _load_subjects(limit: int, offset: int = 0) -> list[dict]:
    factory = get_async_session_factory()
    async with factory() as db:
        rows = (
            await db.scalars(
                select(CoreMetrics)
                .order_by(CoreMetrics.enterprise_id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return [
            {
                "enterprise_id": row.enterprise_id,
                "name": row.display_name or row.enterprise_id,
            }
            for row in rows
        ]


async def run_batch(
    limit: int,
    subject_count: int,
    subject_offset: int = 0,
    profile: str = "default",
) -> dict:
    if os.getenv("STAGING_CONFIRM", "").lower() not in {"1", "true", "yes"}:
        raise SystemExit("STAGING_CONFIRM=true is required")
    if os.getenv("SHADOW_SEMANTIC_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        raise SystemExit("SHADOW_SEMANTIC_ENABLED=true is required")
    if os.getenv("SHADOW_ANSWER_EVAL_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        raise SystemExit("SHADOW_ANSWER_EVAL_ENABLED=true is required")

    subjects = await _load_subjects(subject_count, subject_offset)
    plan = build_query_plan(subjects, profile=profile)[:limit]
    factory = get_async_session_factory()
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    completed = 0
    errors = 0
    async with factory() as db:
        for index, item in enumerate(plan, 1):
            query = item["query"]
            session_id = f"staging-shadow-{batch_id}-{index}"
            started = time.perf_counter()
            try:
                result = await route_chat(
                    db,
                    query,
                    session_id=session_id,
                    enterprise_id=item.get("enterprise_id"),
                    user=None,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                await _maybe_run_shadow(
                    query,
                    result,
                    session_id=session_id,
                    legacy_latency_ms=latency_ms,
                    db=db,
                )
                completed += 1
            except Exception as exc:
                errors += 1
                print(f"[{index}/{len(plan)}] ERROR {item['category']}: {exc}")
            if index % 5 == 0 or index == len(plan):
                print(f"[{index}/{len(plan)}] completed={completed} errors={errors}")

    engine = get_sync_engine()
    return {
        "batch_id": batch_id,
        "profile": profile,
        "planned": len(plan),
        "completed": completed,
        "errors": errors,
        "shadow": build_shadow_evaluation_summary(engine, min_samples=20),
        "answer": build_shadow_answer_summary(engine, min_samples=20),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--subjects", type=int, default=4)
    parser.add_argument("--subject-offset", type=int, default=0)
    parser.add_argument("--profile", choices=["default", "diverse"], default="default")
    args = parser.parse_args()
    report = asyncio.run(
        run_batch(
            limit=args.limit,
            subject_count=args.subjects,
            subject_offset=args.subject_offset,
            profile=args.profile,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["completed"] > 0 else 1)


if __name__ == "__main__":
    main()