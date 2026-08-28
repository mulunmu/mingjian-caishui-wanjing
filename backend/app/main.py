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
from app.api.v1.ingest import router as ingest_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.report import router as report_router
from app.api.v1.risk import router as risk_router
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

基于税务数据的五维风控引擎（评分 / 真实性 / 反欺诈 / 基准 / 趋势）。

### 数据模式
- **mock** — 纯离线演示模式（无后端）
- **mock_with_llm** — 模拟数据 + AI 大模型实时回复
- **live** — 真实税务数据 + AI 大模型

### 认证
演示阶段默认不强制认证。设置 `AUTH_REQUIRED=true` 开启 JWT 保护。
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

        if not rate_limiter.check_api_limit():
            response = JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后重试"})
            await response(scope, receive, send)
            return

        rate_limiter.record_api_call()
        await self.app(scope, receive, send)


app.add_middleware(RateLimitMiddleware)


app.include_router(auth_router, prefix="/api/v1")
app.include_router(risk_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(ingest_router, prefix="/api/v1")


@app.get("/api/v1/health")
async def health():
    database = "disconnected"
    enterprise_count = 0
    engine_features_count = 0
    data_mode = "mock"
    try:
        async with _get_async_session_local() as db:
            await db.execute(text("SELECT 1"))
            database = "connected"
            result = await db.execute(select(func.count()).select_from(CoreMetrics))
            enterprise_count = result.scalar_one()
            data_mode = "live" if enterprise_count > 0 else "mock"
            try:
                from app.models.engine_store import EnterpriseEngineFeatures

                engine_features_count = (
                    await db.execute(select(func.count()).select_from(EnterpriseEngineFeatures))
                ).scalar_one()
            except Exception:
                engine_features_count = 0
    except Exception as e:
        logger.error(f"Health check failed: {type(e).__name__}: {e}", exc_info=True)
        database = "disconnected"
        data_mode = "mock"

    llm_available = is_llm_configured()
    from app.services.cache_service import is_redis_available
    from app.services.rate_limiter import get_llm_usage, redis_backend_active

    return {
        "status": "ok",
        "database": database,
        "enterprise_count": enterprise_count,
        "engine_features_count": engine_features_count,
        "llm_configured": llm_available,
        "data_mode": data_mode if data_mode == "live" else ("mock_with_llm" if llm_available else "mock"),
        "redis": "connected" if is_redis_available() or redis_backend_active() else "memory",
        "llm_usage": get_llm_usage(),
        "mysql_checks": _startup_checks or None,
    }
