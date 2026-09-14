import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.db.session import get_db
from app.responses import UTF8JSONResponse
from app.services import session_store
from app.services.chat_router import route_chat
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

SESSION_NOTE = "会话历史按账号归档保留约 7 天；活跃上下文约 30 分钟"


class ChatRequest(BaseModel):
    query: str = Field(default="", max_length=2000)
    session_id: str | None = None
    enterprise_id: str | None = None
    # 刀 1：结构化追问（drilldown / action / navigate）；与 query 二选一或并用
    followup: dict | None = None


def _owner_from_user(user: dict | None) -> str | None:
    if not user:
        return None
    return (user.get("sub") or user.get("email") or "").strip().lower() or None


@router.get("/sessions", response_class=UTF8JSONResponse)
async def list_chat_sessions(user: dict = Depends(get_current_user)):
    owner = _owner_from_user(user)
    if not owner:
        raise HTTPException(status_code=401, detail="需要登录才能访问此接口")
    sessions = await run_blocking(session_store.list_sessions, owner)
    return {"sessions": sessions}


@router.get("/sessions/{session_id}", response_class=UTF8JSONResponse)
async def get_chat_session(session_id: str, user: dict = Depends(get_current_user)):
    owner = _owner_from_user(user)
    if not owner:
        raise HTTPException(status_code=401, detail="需要登录才能访问此接口")
    data = await run_blocking(session_store.load_history, owner, session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return data


@router.delete("/sessions/{session_id}", response_class=UTF8JSONResponse)
async def delete_chat_session(session_id: str, user: dict = Depends(get_current_user)):
    owner = _owner_from_user(user)
    if not owner:
        raise HTTPException(status_code=401, detail="需要登录才能访问此接口")
    ok = await run_blocking(session_store.delete_session, owner, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return {"ok": True, "session_id": session_id}


@router.post("", response_class=UTF8JSONResponse)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict | None = Depends(get_current_user_optional),
):
    # 全局限流由 RateLimitMiddleware 按 IP 执行；此处不再二次扣全局桶。
    # 每日 LLM 配额耗尽时由 route_chat / generate_claim_reply 经 llm_available() 降级规则模式。

    try:
        result = await route_chat(
            db,
            body.query or (body.followup or {}).get("label") or "",
            session_id=body.session_id,
            enterprise_id=body.enterprise_id,
            user=_user,
            followup=body.followup,
        )
    except Exception as exc:
        logger.warning("chat route failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="对话服务暂不可用，请稍后重试。演示数据不会在服务端伪造返回。",
        ) from exc

    result["session_note"] = SESSION_NOTE
    reply = (result.get("reply") or "").strip()
    logger.info("chat reply[:200]=%r", reply[:200])
    return result
