"""PostgreSQL 同步连接 URL + 模块级 Engine 单例（热路径复用连接池）。"""
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine


def sync_database_url() -> str:
    """从 DATABASE_URL_SYNC 或 DATABASE_URL 派生同步连接串。"""
    return os.getenv(
        "DATABASE_URL_SYNC",
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://risk_user:risk_pass@localhost:5432/risk_db",
        ).replace("postgresql+asyncpg://", "postgresql://"),
    )


@lru_cache(maxsize=1)
def get_sync_engine() -> Engine:
    """进程内单例 Engine；pool_pre_ping 避免脏连接。"""
    return create_engine(
        sync_database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


# 兼容旧名
def pg_url() -> str:
    return sync_database_url()
