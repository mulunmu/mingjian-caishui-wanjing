"""指标语义层 API：口径字典导出（阶段二）。

字典只含元数据，供 LLM 上下文 / 数据接入字段映射使用，不含任何原始数据 / PII。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.models.metric_registry import MetricDefinition
from app.services.metric_registry import build_dictionary

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/dictionary")
async def get_metric_dictionary(
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    """返回规范口径字典（指标 + 源字段 + 维度），供 LLM 上下文与字段映射。"""
    try:
        rows = list((await db.execute(select(MetricDefinition))).scalars().all())
    except Exception as exc:
        logger.warning("metric dictionary DB read failed: %s", exc)
        raise HTTPException(status_code=503, detail="口径字典暂不可用，请稍后重试。") from exc
    return build_dictionary(rows)
