import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_optional
from app.db.session import get_async_session_factory, get_db
from app.responses import UTF8JSONResponse
from app.services import session_store
from app.services.progress import ProgressScope, emit_progress
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

SESSION_NOTE = "会话历史按账号归档保留约 7 天；活跃上下文约 30 分钟"


class ChatRequest(BaseModel):
    query: str = Field(default="", max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)
    enterprise_id: str | None = None
    approval: bool | None = None
    # 刀 1：结构化追问（drilldown / action / navigate）；与 query 二选一或并用
    followup: dict | None = None


def _owner_from_user(user: dict | None) -> str | None:
    if not user:
        return None
    return (user.get("sub") or user.get("email") or "").strip().lower() or None

async def _maybe_run_primary(
    query: str,
    *,
    session_id: str,
    owner: str | None,
    user: dict | None = None,
    enterprise_id: str | None,
    approval: bool | None = None,
    db=None,
) -> dict | None:
    from app.services import semantic_primary
    from app.services import outer_orchestrator

    if not semantic_primary.primary_enabled():
        return None
    if not semantic_primary.primary_selected(session_id):
        return None
    return await outer_orchestrator.run_outer_turn(
        db=db,
        session_id=session_id,
        owner=owner,
        query=query,
        enterprise_id=enterprise_id,
        user=user,
        approval=approval,
    )


@router.get("/sessions", response_class=UTF8JSONResponse)
async def list_chat_sessions(user: dict = Depends(get_current_user)):
    owner = _owner_from_user(user)
    if not owner:
        raise HTTPException(status_code=401, detail="需要登录才能访问此接口")
    sessions = await run_blocking(session_store.list_sessions, owner)
    return {"sessions": sessions}


@router.get("/bootstrap", response_class=UTF8JSONResponse)
async def bootstrap_chat_session(
    session_id: str | None = None,
    user: dict | None = Depends(get_current_user_optional),
):
    """Return session UI state without creating a visible conversation turn."""
    from app.services import scope_state

    owner = _owner_from_user(user)
    sid = await run_blocking(session_store.ensure_session_id, session_id, owner)
    session = await run_blocking(session_store.get_session, sid) or {}
    state = session.get("dialogue_state") or {}
    ui = scope_state.ui_bundle(state)
    from app.services import llm_reply

    scope_name = state.get("scope") or "unbound"
    subject = state.get("subject") or {}
    facts = (
        f"当前会话范围：{scope_name}；"
        f"当前主体：{subject.get('display_name') or '未绑定'}；"
        "可以介绍系统能协助财务、税务、发票、真实性、风险信号、评级和报告分析，"
        "并给出下一步可选动作，但不要编造企业、数字或分析结论。"
    )
    welcome, welcome_source = await llm_reply.generate_policy_reply(
        query="准备开始新的会话",
        route="greeting",
        facts=facts,
        status="answered",
    )
    if welcome:
        ui["welcome"] = welcome
    else:
        ui["welcome"] = ""
    return {
        "session_id": sid,
        "dialogue_state": scope_state.state_public(state),
        "ui": ui,
        "welcome_source": welcome_source,
    }


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
    scope = ProgressScope()
    with scope:
        primary_result = await _execute_chat_turn(body=body, db=db, user=_user)
    primary_result["process"] = scope.events
    return primary_result


async def _execute_chat_turn(*, body: ChatRequest, db, user: dict | None) -> dict:
    # Stage 9：活动入口只允许 semantic primary；旧路由不得作为隐式兜底。

    query = body.query or (body.followup or {}).get("label") or ""
    started = time.perf_counter()
    owner = _owner_from_user(user)
    sid = await run_blocking(session_store.ensure_session_id, body.session_id, owner)
    if isinstance(body.followup, dict) and body.followup.get("type") == "switch_scope":
        from app.services.scope_control import handle_scope_change

        await emit_progress("scope", "正在切换分析范围")
        return await handle_scope_change(
            db=db,
            session_id=sid,
            owner=owner,
            followup=body.followup,
        )
    await emit_progress("intent", "正在理解问题", "识别会话意图、主体和分析范围")
    try:
        primary_result = await _maybe_run_primary(
            query,
            session_id=sid,
            owner=owner,
            user=user,
            enterprise_id=body.enterprise_id,
            approval=body.approval,
            db=db,
        )
    except Exception as exc:
        logger.warning("semantic primary failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="对话服务暂不可用，请稍后重试。演示数据不会在服务端伪造返回。",
        ) from exc

    if primary_result is None:
        raise HTTPException(
            status_code=503,
            detail="对话服务未启用语义主路径，请检查服务配置后重试。",
        )

    primary_result["session_note"] = SESSION_NOTE
    reply = (primary_result.get("reply") or "").strip()
    logger.info(
        "semantic chat reply[:200]=%r latency_ms=%.1f",
        reply[:200],
        (time.perf_counter() - started) * 1000,
    )
    from app.services import scope_state

    session = await run_blocking(session_store.get_session, sid) or {}
    state = session.get("dialogue_state") or {}
    primary_result["dialogue_state"] = scope_state.state_public(state)
    primary_result["ui"] = scope_state.ui_bundle(state)
    return primary_result


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: dict | None = Depends(get_current_user_optional),
):
    async def event_stream():
        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def emit(event: dict) -> None:
            await queue.put(("progress", event))

        async def run_turn() -> None:
            scope = ProgressScope(emitter=emit)
            try:
                with scope:
                    async with get_async_session_factory()() as stream_db:
                        result = await _execute_chat_turn(
                            body=body,
                            db=stream_db,
                            user=user,
                        )
                result["process"] = scope.events
                await queue.put(("result", result))
            except Exception as exc:
                logger.exception("stream chat turn failed")
                await queue.put(
                    (
                        "error",
                        {
                            "detail": "对话服务暂不可用，请稍后重试。",
                            "error_type": type(exc).__name__,
                        },
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(run_turn())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event_name, payload = item
                data = json.dumps(payload, ensure_ascii=False, default=str)
                yield f"event: {event_name}\ndata: {data}\n\n"
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
