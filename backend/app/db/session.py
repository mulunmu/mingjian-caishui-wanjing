import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://risk_user:risk_pass@localhost:5432/risk_db",
)

_engine = None
_SessionLocal = None


def _pool_kwargs() -> dict:
    """连接池参数；DB_POOL_DISABLED=true 时回退 NullPool（仅调试）。"""
    if os.getenv("DB_POOL_DISABLED", "").lower() in ("1", "true", "yes"):
        from sqlalchemy.pool import NullPool

        return {"poolclass": NullPool}
    return {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_POOL_MAX_OVERFLOW", "10")),
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
    }


def _ensure_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_async_engine(DATABASE_URL, echo=False, **_pool_kwargs())
        _SessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine, _SessionLocal


def get_async_session_factory():
    """返回 async_sessionmaker，供依赖注入使用。"""
    _, factory = _ensure_engine()
    return factory


def _get_async_session_local() -> AsyncSession:
    """兼容旧调用：从连接池取新 AsyncSession。"""
    return get_async_session_factory()()


async def get_db():
    async with _get_async_session_local() as session:
        yield session


async def dispose_db_engine() -> None:
    """应用关闭时释放连接池。"""
    global _engine, _SessionLocal
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _SessionLocal = None
