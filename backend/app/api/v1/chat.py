import logging
import os
import time

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

def _shadow_semantic_enabled() -> bool:
    return os.getenv("SHADOW_SEMANTIC_ENABLED", "false").lower() in {"1", "true", "yes"}


def _shadow_answer_eval_enabled() -> bool:
    return os.getenv("SHADOW_ANSWER_EVAL_ENABLED", "false").lower() in {"1", "true", "yes"}


def _shadow_independent_route_enabled() -> bool:
    return os.getenv("SHADOW_SEMANTIC_INDEPENDENT_ROUTE", "true").lower() in {
        "1",
        "true",
        "yes",
    }


async def _resolve_shadow_raw_route(query: str) -> dict | None:
    if not _shadow_independent_route_enabled():
        return None
    try:
        from app.services import dialog_act
        from app.services.shadow_integration import dialog_act_to_raw_route

        act = await dialog_act.classify(query)
        return dialog_act_to_raw_route(act, query)
    except Exception as exc:
        logger.warning("independent shadow route failed, falling back to legacy route: %s", exc)
        return None


async def _maybe_run_shadow(
    query: str,
    result: dict,
    *,
    session_id: str | None,
    legacy_latency_ms: float,
    db=None,
) -> None:
    if not _shadow_semantic_enabled():
        return
    try:
        from app.db.urls import get_sync_engine
        from app.services.shadow_integration import run_shadow_evaluation_sync

        raw_route = await _resolve_shadow_raw_route(query)
        await run_blocking(
            run_shadow_evaluation_sync,
            get_sync_engine(),
            query,
            result,
            session_id=session_id,
            legacy_latency_ms=legacy_latency_ms,
            raw_route=raw_route,
        )
        if _shadow_answer_eval_enabled() and db is not None and raw_route is not None:
            from app.services.shadow_answer_evaluation import (
                evaluate_shadow_answer,
                save_shadow_answer_observation,
            )

            observation = await evaluate_shadow_answer(
                db=db,
                session_id=session_id or "",
                query=query,
                raw_route=raw_route,
            )
            await run_blocking(
                save_shadow_answer_observation,
                get_sync_engine(),
                observation,
            )
    except Exception as exc:
        logger.warning("shadow semantic evaluation skipped: %s", exc)

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

    query = body.query or (body.followup or {}).get("label") or ""
    started = time.perf_counter()
    try:
        result = await route_chat(
            db,
            query,
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

    legacy_latency_ms = (time.perf_counter() - started) * 1000
    await _maybe_run_shadow(
        query,
        result,
        session_id=result.get("session_id") or body.session_id,
        legacy_latency_ms=legacy_latency_ms,
        db=db,
    )
    result["session_note"] = SESSION_NOTE
    reply = (result.get("reply") or "").strip()
    logger.info("chat reply[:200]=%r", reply[:200])
    return result
