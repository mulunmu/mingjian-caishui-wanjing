"""异动订阅：定制用户订阅企业 → 数据刷新检测异动 → 自动出报告并推送。

铁律：
- 订阅是定制（subscriber）用户专属能力，归属以 AppUser.email 为 key；
- 异动判定复用 anomaly_detection 的确定性规则，弃权优先于编造；
- 推送仅在检测到「实质异动」（高危信号，或信号数达阈值）时触发，不滥发。
"""
from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics, LegalEvent
from app.models.financials import EnterpriseFinancials
from app.models.subscription import Subscription
from app.services import anomaly_detection, insight_engine

logger = logging.getLogger(__name__)


def _demo_user_id() -> str:
    """演示态（AUTH_REQUIRED=false 未登录）归属到演示用户，便于开发验证。"""
    return (os.getenv("DEMO_USER_EMAIL") or "admin@example.com").strip().lower()


def resolve_user_id(user: dict | None) -> str:
    if user:
        return (user.get("sub") or user.get("email") or _demo_user_id()).strip().lower()
    return _demo_user_id()


async def list_active_subscriptions(
    db: AsyncSession, user_id: str
) -> list[Subscription]:
    rows = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.active.is_(True),
        )
    )
    return list(rows.scalars().all())


async def build_enterprise_signals(
    db: AsyncSession, enterprise_id: str
) -> list[dict[str, Any]]:
    """加载个体 L0 数据并产出异动信号（供订阅推送与 /enterprise 信号面板复用）。"""
    metrics, features = await insight_engine.load_insight_inputs(db, enterprise_id)
    insights = insight_engine.evaluate_insights(metrics, features) if metrics else []
    financials = await db.get(EnterpriseFinancials, enterprise_id)

    events: list[LegalEvent] = []
    if metrics is not None:
        rows = await db.execute(
            select(LegalEvent).where(LegalEvent.enterprise_id == enterprise_id)
        )
        events = list(rows.scalars().all())

    return anomaly_detection.detect_anomalies(metrics, financials, insights, events)


async def run_subscription_detection(
    db: AsyncSession, user_id: str, *, send_email: bool = False
) -> dict[str, Any]:
    """对某用户全部订阅企业跑异动检测，实质异动时生成报告（可选推送）。

    返回逐企业汇总；生成报告复用 slice_report.generate_enterprise_report。
    """
    subs = await list_active_subscriptions(db, user_id)
    results: list[dict[str, Any]] = []
    pushed = 0
    for sub in subs:
        signals = await build_enterprise_signals(db, sub.enterprise_id)
        high = sum(1 for s in signals if s["level"] == "high")
        material = anomaly_detection.has_material_anomaly(signals)
        entry: dict[str, Any] = {
            "enterprise_id": sub.enterprise_id,
            "signals": signals,
            "signal_count": len(signals),
            "high_count": high,
            "material": material,
            "report_id": None,
            "pushed": False,
        }
        if material:
            try:
                from app.services.slice_report import generate_enterprise_report

                report_id, pdf_path, ctx = await generate_enterprise_report(
                    db, sub.enterprise_id, owner=user_id
                )
                entry["report_id"] = report_id
                if send_email:
                    from app.services import email_service

                    if email_service.is_configured():
                        from app.services.sync_runner import run_blocking

                        await run_blocking(
                            email_service.send_slice_report,
                            user_id,
                            str(ctx.get("title") or "异动风控报告"),
                            pdf_path,
                        )
                        entry["pushed"] = True
                        pushed += 1
                    else:
                        logger.info("email not configured; skip push for %s", sub.enterprise_id)
            except Exception as exc:  # 单企业失败不阻断整体
                logger.warning("subscription detect failed for %s: %s", sub.enterprise_id, exc)
                entry["error"] = str(exc)
        results.append(entry)
    return {"user_id": user_id, "total": len(results), "pushed": pushed, "items": results}
