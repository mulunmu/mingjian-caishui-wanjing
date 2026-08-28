"""异动订阅 API（定制用户专属）：订阅/退订/列表/触发检测。

- 订阅关系以 user_id = AppUser.email 为 key（演示态未登录归属到演示用户）。
- 检测复用 subscription_service.run_subscription_detection，实质异动时生成报告并可推送。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_plan
from app.db.session import get_db
from app.models.core_metrics import CoreMetrics
from app.models.subscription import Subscription
from app.services import subscription_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

_plan = require_plan("subscriber")


class SubscribeRequest(BaseModel):
    enterprise_id: str


class DetectRequest(BaseModel):
    send_email: bool = False


@router.post("")
async def subscribe(
    body: SubscribeRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(_plan),
):
    """订阅企业（幂等）：已存在则返回既有关系。"""
    user_id = subscription_service.resolve_user_id(_user)
    enterprise = await db.get(CoreMetrics, body.enterprise_id)
    if not enterprise:
        raise HTTPException(status_code=404, detail="未找到该匿名样本。")

    existing = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.enterprise_id == body.enterprise_id,
        )
    )
    rec = existing.scalars().first()
    if rec is not None:
        if not rec.active:
            rec.active = True
            await db.commit()
        return {"subscribed": True, "enterprise_id": rec.enterprise_id, "already": True}

    sub = Subscription(user_id=user_id, enterprise_id=body.enterprise_id, active=True)
    db.add(sub)
    await db.commit()
    return {"subscribed": True, "enterprise_id": sub.enterprise_id, "already": False}


@router.get("")
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(_plan),
):
    """列出我的订阅，并附当前异动信号概要。"""
    user_id = subscription_service.resolve_user_id(_user)
    subs = await subscription_service.list_active_subscriptions(db, user_id)
    items = []
    for sub in subs:
        enterprise = await db.get(CoreMetrics, sub.enterprise_id)
        signals = await subscription_service.build_enterprise_signals(db, sub.enterprise_id)
        high = sum(1 for s in signals if s["level"] == "high")
        items.append(
            {
                "enterprise_id": sub.enterprise_id,
                "display_label": enterprise.display_label if enterprise else "",
                "industry_l1": enterprise.industry_l1 if enterprise else "",
                "signal_count": len(signals),
                "high_count": high,
                "material": subscription_service.anomaly_detection.has_material_anomaly(signals),
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
            }
        )
    return {"items": items, "total": len(items)}


@router.delete("/{enterprise_id}")
async def unsubscribe(
    enterprise_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(_plan),
):
    """退订（软删除 active=False，保留归属历史）。"""
    user_id = subscription_service.resolve_user_id(_user)
    existing = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.enterprise_id == enterprise_id,
        )
    )
    rec = existing.scalars().first()
    if rec is None or not rec.active:
        return {"unsubscribed": False}
    rec.active = False
    await db.commit()
    return {"unsubscribed": True}


@router.post("/detect")
async def detect(
    body: DetectRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(_plan),
):
    """对全部订阅企业跑异动检测；实质异动时生成报告（可选邮件推送）。"""
    user_id = subscription_service.resolve_user_id(_user)
    try:
        return await subscription_service.run_subscription_detection(
            db, user_id, send_email=body.send_email
        )
    except Exception as exc:
        logger.warning("subscription detect failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"异动检测失败: {exc}") from exc
