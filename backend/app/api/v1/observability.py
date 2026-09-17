"""Admin-only runtime observability snapshot."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.services.observability import metrics_snapshot


router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics")
async def get_runtime_metrics(user: dict | None = Depends(get_current_user)):
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return metrics_snapshot()
