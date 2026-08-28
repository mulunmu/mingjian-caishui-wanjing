"""调用次数限制 — LLM 每日上限 + 通用 API 速率限制

设置 REDIS_URL 后跨进程共享；未设置则进程内内存（单测/单实例演示）。
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date

logger = logging.getLogger(__name__)

LLM_DAILY_LIMIT = int(os.getenv("LLM_DAILY_LIMIT", "1000"))
API_RATE_PER_SECOND = int(os.getenv("API_RATE_PER_SECOND", "20"))

_llm_counters: dict[str, int] = {}
_request_timestamps: list[float] = []
_redis = None
_redis_checked = False


def _get_redis():
    global _redis, _redis_checked
    if _redis_checked:
        return _redis
    _redis_checked = True
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis

        client = redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        _redis = client
        logger.info("rate_limiter using Redis")
    except Exception as exc:
        logger.warning("REDIS_URL set but unavailable (%s); memory fallback", exc)
        _redis = None
    return _redis


def _today_key() -> str:
    return date.today().isoformat()


def _reset_if_new_day() -> None:
    today = _today_key()
    stale = [k for k in _llm_counters if k != today]
    for k in stale:
        del _llm_counters[k]
    _llm_counters.setdefault(today, 0)


def check_llm_limit() -> bool:
    r = _get_redis()
    if r is not None:
        try:
            used = int(r.get(f"llm:daily:{_today_key()}") or 0)
            return used < LLM_DAILY_LIMIT
        except Exception:
            pass
    _reset_if_new_day()
    return _llm_counters[_today_key()] < LLM_DAILY_LIMIT


def increment_llm() -> int:
    r = _get_redis()
    if r is not None:
        try:
            key = f"llm:daily:{_today_key()}"
            used = int(r.incr(key))
            if used == 1:
                r.expire(key, 86400 + 3600)
            return used
        except Exception:
            pass
    _reset_if_new_day()
    key = _today_key()
    _llm_counters[key] = _llm_counters.get(key, 0) + 1
    return _llm_counters[key]


def get_llm_usage() -> dict:
    r = _get_redis()
    if r is not None:
        try:
            used = int(r.get(f"llm:daily:{_today_key()}") or 0)
            return {
                "date": _today_key(),
                "used": used,
                "limit": LLM_DAILY_LIMIT,
                "remaining": max(0, LLM_DAILY_LIMIT - used),
                "backend": "redis",
            }
        except Exception:
            pass
    _reset_if_new_day()
    used = _llm_counters.get(_today_key(), 0)
    return {
        "date": _today_key(),
        "used": used,
        "limit": LLM_DAILY_LIMIT,
        "remaining": max(0, LLM_DAILY_LIMIT - used),
        "backend": "memory",
    }


def check_api_limit() -> bool:
    """滑动 1 秒窗口。"""
    r = _get_redis()
    now = time.time()
    if r is not None:
        try:
            key = "api:ratelimit"
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - 1.0)
            pipe.zcard(key)
            results = pipe.execute()
            return int(results[1]) < API_RATE_PER_SECOND
        except Exception:
            pass
    cutoff = now - 1.0
    while _request_timestamps and _request_timestamps[0] < cutoff:
        _request_timestamps.pop(0)
    return len(_request_timestamps) < API_RATE_PER_SECOND


def record_api_call() -> None:
    r = _get_redis()
    now = time.time()
    if r is not None:
        try:
            key = "api:ratelimit"
            member = f"{now:.6f}:{os.getpid()}"
            pipe = r.pipeline()
            pipe.zadd(key, {member: now})
            pipe.zremrangebyscore(key, 0, now - 1.0)
            pipe.expire(key, 2)
            pipe.execute()
            return
        except Exception:
            pass
    _request_timestamps.append(now)


def redis_backend_active() -> bool:
    return _get_redis() is not None


# 向后兼容别名
check_limit = check_llm_limit
increment = increment_llm
