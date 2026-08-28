import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.db.session import get_db
from app.responses import UTF8JSONResponse
from app.services.chat_router import route_chat
from app.services import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

SESSION_NOTE = "会话记忆持久化于 PostgreSQL（TTL 约 30 分钟无活跃则过期）"


class ChatRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    session_id: str | None = None
    enterprise_id: str | None = None


@router.post("", response_class=UTF8JSONResponse)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db), _user: dict | None = Depends(get_current_user_optional)):
    if not rate_limiter.check_api_limit():
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后重试")
    # 每日 LLM 配额耗尽时不再硬抛 429，而是由 route_chat / generate_claim_reply 内部
    # 经 llm_available() 判断自动降级到规则模式（仍能回答，只是少了 LLM 润色）。

    try:
        result = await route_chat(
            db, body.query, session_id=body.session_id, enterprise_id=body.enterprise_id
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
