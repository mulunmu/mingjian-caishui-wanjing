import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# 在最前面加载 .env，确保 app.db.session 等模块级 os.getenv 在导入前已读到配置
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.email import router as email_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.report import router as report_router
from app.api.v1.risk import router as risk_router
from app.api.v1.subscription import router as subscription_router
from app.db.session import _get_async_session_local
from app.models.core_metrics import CoreMetrics
from app.responses import UTF8JSONResponse
from app.services.llm_reply import is_llm_configured
from app.services import rate_limiter

logger = logging.getLogger(__name__)

_startup_checks: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.db.mysql_encoding import run_startup_checks

    global _startup_checks
    try:
        _startup_checks = await asyncio.to_thread(run_startup_checks)
        if not _startup_checks.get("ok"):
            logger.warning("MySQL startup self-check reported issues: %s", _startup_checks)
    except Exception as exc:
        logger.warning("MySQL startup self-check skipped: %s", exc)
        _startup_checks = {"ok": False, "error": str(exc)}

    if os.getenv("MYSQL_REDACT_ON_STARTUP", "true").lower() in ("1", "true", "yes"):
        try:
            from app.services.mysql_redaction import run_startup_redaction

            redact = await asyncio.to_thread(run_startup_redaction)
            _startup_checks["mysql_redaction"] = redact
        except Exception as exc:
            logger.warning("MySQL startup redaction skipped: %s", exc)
            _startup_checks["mysql_redaction"] = {"applied": False, "error": str(exc)}

    try:
        from app.db.session import Base
        from app.db.urls import get_sync_engine
        import app.models  # noqa: F401 — 注册 engine_store / core_metrics

        eng = get_sync_engine()
        await asyncio.to_thread(Base.metadata.create_all, eng)

        def _ensure_chat_session_columns() -> None:
            """已有库 create_all 不会加列；补 enterprise_id（S1）。"""
            from sqlalchemy import text

            with eng.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE chat_sessions "
                        "ADD COLUMN IF NOT EXISTS enterprise_id VARCHAR(64)"
                    )
                )

        try:
            await asyncio.to_thread(_ensure_chat_session_columns)
        except Exception as col_exc:
            logger.debug("chat_sessions column ensure: %s", col_exc)

        def _ensure_chat_session_custom_state_column() -> None:
            """已有库 create_all 不会加列；补 chat_sessions.custom_state_json（定制报告对话态）。"""
            from sqlalchemy import text

            with eng.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE chat_sessions "
                        "ADD COLUMN IF NOT EXISTS custom_state_json TEXT"
                    )
                )

        try:
            await asyncio.to_thread(_ensure_chat_session_custom_state_column)
        except Exception as col_exc:
            logger.debug("chat_sessions custom_state column ensure: %s", col_exc)

        def _ensure_chat_session_owner_column() -> None:
            """已有库 create_all 不会加列；补 chat_sessions.owner（M0 账号记忆）。"""
            from sqlalchemy import text

            with eng.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE chat_sessions "
                        "ADD COLUMN IF NOT EXISTS owner VARCHAR(255)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_chat_sessions_owner "
                        "ON chat_sessions (owner)"
                    )
                )

        try:
            await asyncio.to_thread(_ensure_chat_session_owner_column)
        except Exception as col_exc:
            logger.debug("chat_sessions owner column ensure: %s", col_exc)

        def _ensure_app_user_plan_column() -> None:
            """已有库 create_all 不会加列；补 app_users.plan（订阅分层）。"""
            from sqlalchemy import text

            with eng.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE app_users "
                        "ADD COLUMN IF NOT EXISTS plan VARCHAR(32) NOT NULL DEFAULT 'free'"
                    )
                )

        try:
            await asyncio.to_thread(_ensure_app_user_plan_column)
        except Exception as col_exc:
            logger.debug("app_users plan column ensure: %s", col_exc)

        def _ensure_app_user_pwd_ver_column() -> None:
            """已有库 create_all 不会加列；补 app_users.pwd_ver（改密后旧 token 失效）。"""
            from sqlalchemy import text

            with eng.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE app_users "
                        "ADD COLUMN IF NOT EXISTS pwd_ver INTEGER NOT NULL DEFAULT 0"
                    )
                )

        try:
            await asyncio.to_thread(_ensure_app_user_pwd_ver_column)
        except Exception as col_exc:
            logger.debug("app_users pwd_ver column ensure: %s", col_exc)

        from app.services.auth_service import ensure_demo_user, validate_production_config

        auth_check = validate_production_config()
        _startup_checks["auth_config"] = auth_check
        if auth_check.get("auth_required") and not auth_check.get("ok"):
            msg = "; ".join(auth_check.get("errors") or [])
            raise RuntimeError(f"Production auth config invalid: {msg}")

        await asyncio.to_thread(ensure_demo_user)

        from app.services.metric_registry import ensure_canonical_metrics

        _startup_checks["canonical_metrics_seeded"] = await asyncio.to_thread(ensure_canonical_metrics)
    except RuntimeError:
        raise
    except Exception as exc:
        logger.debug("PG create_all on startup: %s", exc)
    yield
    try:
        from app.db.session import dispose_db_engine

        await dispose_db_engine()
    except Exception as exc:
        logger.debug("DB engine dispose: %s", exc)


app = FastAPI(
    title="明鉴・财税票・万景",
    description="""## 明鉴・财税票・万景 API

基于税务数据的六维风控引擎（评分 / 真实性 / 反欺诈 / 基准 / 趋势）。

### 数据模式
- **mock** — 纯离线演示模式（无后端）
- **mock_with_llm** — 模拟数据 + AI 大模型实时回复
- **live** — 真实税务数据 + AI 大模型

### 认证
演示默认开启 JWT（`AUTH_REQUIRED=true`）。本地无鉴权调试请显式设 `AUTH_REQUIRED=false`。
""",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=UTF8JSONResponse,
    lifespan=lifespan,
)

# CORS — 演示默认 *；生产 AUTH_REQUIRED=true 时须显式设置 CORS_ORIGINS
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API 速率限制中间件（纯 ASGI，避免 BaseHTTPMiddleware 与 asyncpg 事件循环冲突）
from starlette.types import ASGIApp, Receive, Scope, Send


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/api/v1/health":
            await self.app(scope, receive, send)
            return

        client_key = _client_key_from_scope(scope)
        rate_limiter.set_request_client_key(client_key)
        if not rate_limiter.check_api_limit(client_key):
            response = JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后重试"})
            await response(scope, receive, send)
            return

        rate_limiter.record_api_call(client_key)
        await self.app(scope, receive, send)


def _client_key_from_scope(scope: Scope) -> str:
    """限流键：默认用直连 peer；仅 TRUST_PROXY=true 时信任 X-Forwarded-For。"""
    client = scope.get("client")
    peer = client[0] if client and client[0] else "unknown"
    if os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes"):
        headers = {k.decode().lower(): v.decode() for k, v in (scope.get("headers") or [])}
        forwarded = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return f"ip:{forwarded}"
    return f"ip:{peer}"


app.add_middleware(RateLimitMiddleware)


app.include_router(auth_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")
app.include_router(email_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(ingest_router, prefix="/api/v1")
app.include_router(subscription_router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health():
    database = "disconnected"
    data_mode = "mock"
    try:
        async with _get_async_session_local() as db:
            await db.execute(text("SELECT 1"))
            database = "connected"
            result = await db.execute(select(func.count()).select_from(CoreMetrics))
            enterprise_count = result.scalar_one()
            data_mode = "live" if enterprise_count > 0 else "mock"
    except Exception as e:
        logger.error(f"Health check failed: {type(e).__name__}: {e}", exc_info=True)
        database = "disconnected"
        data_mode = "mock"

    llm_available = is_llm_configured()
    from app.services.cache_service import is_redis_available
    from app.services.rate_limiter import redis_backend_active

    return {
        "status": "ok",
        "database": database,
        "llm_configured": llm_available,
        "data_mode": data_mode if data_mode == "live" else ("mock_with_llm" if llm_available else "mock"),
        "redis": "connected" if is_redis_available() or redis_backend_active() else "memory",
    }
