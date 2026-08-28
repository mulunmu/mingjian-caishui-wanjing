"""缓存服务 — 内存默认；设置 REDIS_URL 启用 Redis（同步 + 异步）"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "").strip()

_async_client = None
_sync_client = None
_sync_checked = False

if REDIS_URL:
    try:
        import redis.asyncio as aioredis

        _async_client = aioredis.from_url(REDIS_URL)
    except Exception as exc:
        logger.warning("async redis init failed: %s", exc)
        _async_client = None

_store: dict[str, tuple[Any, float | None]] = {}


def _get_sync_redis():
    global _sync_client, _sync_checked
    if _sync_checked:
        return _sync_client
    _sync_checked = True
    if not REDIS_URL:
        return None
    try:
        import redis

        client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        _sync_client = client
    except Exception as exc:
        logger.warning("sync redis unavailable: %s", exc)
        _sync_client = None
    return _sync_client


def get_sync(key: str) -> Any | None:
    r = _get_sync_redis()
    if r is not None:
        try:
            raw = r.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    entry = _store.get(key)
    if entry is None:
        return None
    val, expires_at = entry
    if expires_at and time.time() > expires_at:
        del _store[key]
        return None
    return val


def set_sync(key: str, value: Any, ttl_seconds: int = 300) -> None:
    r = _get_sync_redis()
    if r is not None:
        try:
            payload = json.dumps(value, default=str)
            if ttl_seconds > 0:
                r.setex(key, ttl_seconds, payload)
            else:
                r.set(key, payload)
            return
        except Exception:
            pass
    expires_at = time.time() + ttl_seconds if ttl_seconds > 0 else None
    _store[key] = (value, expires_at)


def delete_sync(key: str) -> None:
    r = _get_sync_redis()
    if r is not None:
        try:
            r.delete(key)
            return
        except Exception:
            pass
    _store.pop(key, None)


async def get(key: str) -> Any | None:
    if _async_client:
        try:
            raw = await _async_client.get(key)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode()
            return json.loads(raw)
        except Exception:
            pass
    return get_sync(key)


async def set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    if _async_client:
        try:
            payload = json.dumps(value, default=str)
            if ttl_seconds > 0:
                await _async_client.setex(key, ttl_seconds, payload)
            else:
                await _async_client.set(key, payload)
            return
        except Exception:
            pass
    set_sync(key, value, ttl_seconds)


async def delete(key: str) -> None:
    if _async_client:
        try:
            await _async_client.delete(key)
            return
        except Exception:
            pass
    delete_sync(key)


def is_redis_available() -> bool:
    return _get_sync_redis() is not None or _async_client is not None
