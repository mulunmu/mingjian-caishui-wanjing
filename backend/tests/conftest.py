import os

import pytest


def pytest_configure(config):
    # 单测默认关闭鉴权，避免模块 import 时 AUTH_REQUIRED 代码默认 true 拖垮契约测试
    os.environ.setdefault("AUTH_REQUIRED", "false")
    # 测试会跨多个 TestClient/事件循环复用全局 async engine；NullPool 避免
    # 连接绑定到已关闭循环。生产环境仍使用默认 QueuePool。
    os.environ.setdefault("DB_POOL_DISABLED", "true")
    # Stage 9 后活动入口为 fail-closed；契约测试默认启用 semantic primary。
    os.environ.setdefault("SEMANTIC_PRIMARY_ENABLED", "true")
    os.environ.setdefault("SEMANTIC_PRIMARY_PERCENT", "100")
    config.addinivalue_line("markers", "llm: optional LLM integration (requires LLM_API_KEY)")


@pytest.fixture
def llm_api_key():
    key = os.getenv("LLM_API_KEY", "")
    if not key or key == "your-api-key-here":
        pytest.skip("LLM_API_KEY not configured")
    return key


@pytest.fixture
async def live_db():
    """真实 PostgreSQL 会话工厂；库不可达则跳过（CI/无库环境只跑纯单测）。"""
    pytest.importorskip("asyncpg")
    from sqlalchemy import text

    from app.db.session import get_async_session_factory

    fac = get_async_session_factory()
    try:
        async with fac() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("no live PostgreSQL (DATABASE_URL unreachable)")
    return fac
