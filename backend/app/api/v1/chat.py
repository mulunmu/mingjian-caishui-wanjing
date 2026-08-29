import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.responses import UTF8JSONResponse
from app.services.chat_router import route_chat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

SESSION_NOTE = "会话记忆持久化于 PostgreSQL（TTL 约 30 分钟无活跃则过期）"


class ChatRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    session_id: str | None = None
    enterprise_id: str | None = None


@router.post("", response_class=UTF8JSONResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db), _user: dict | None = Depends(get_current_user_optional)):
    # 全局限流由 RateLimitMiddleware 按 IP 执行；此处不再二次扣全局桶。
    # 每日 LLM 配额耗尽时由 route_chat / generate_claim_reply 经 llm_available() 降级规则模式。

    try:
        result = await route_chat(
            db,
            body.query,
            session_id=body.session_id,
            enterprise_id=body.enterprise_id,
            user=_user,
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
