"""调用次数限制 — LLM 每日上限 + 通用 API 速率限制（按客户端键隔离）

设置 REDIS_URL 后跨进程共享；未设置则进程内内存（单测/单实例演示）。
客户端键优先：user_id / IP，避免单用户耗尽全员额度。
中间件通过 set_request_client_key 写入 ContextVar，llm_reply 默认按请求键计数。
"""
from __future__ import annotations

import contextvars
import logging
import os
import time
from datetime import date

logger = logging.getLogger(__name__)

LLM_DAILY_LIMIT = int(os.getenv("LLM_DAILY_LIMIT", "1000"))
API_RATE_PER_SECOND = int(os.getenv("API_RATE_PER_SECOND", "20"))
# 单键 LLM 日上限（默认等于全局；可设更小防止单 IP 吃满）
LLM_DAILY_LIMIT_PER_KEY = int(os.getenv("LLM_DAILY_LIMIT_PER_KEY", str(LLM_DAILY_LIMIT)))

_llm_counters: dict[str, int] = {}
_request_timestamps: dict[str, list[float]] = {}
_redis = None
_redis_checked = False
_request_client_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rate_limit_client_key", default=None
)


def set_request_client_key(client_key: str | None) -> None:
    """由 RateLimitMiddleware 在每个请求设置；LLM 配额默认读此键。"""
    _request_client_key.set(client_key)


def current_client_key() -> str | None:
    return _request_client_key.get()


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


def _safe_key(client_key: str | None) -> str:
    raw = (client_key if client_key is not None else current_client_key() or "anon").strip()[:128] or "anon"
    return "".join(c if c.isalnum() or c in "._-:@" else "_" for c in raw)


def _reset_if_new_day() -> None:
    today = _today_key()
    prefix = f"{today}:"
    stale = [k for k in _llm_counters if not k.startswith(prefix) and ":" in k]
    # also legacy day-only keys
    stale += [k for k in _llm_counters if k == today or (len(k) == 10 and k.count("-") == 2 and ":" not in k)]
    for k in stale:
        del _llm_counters[k]


def check_llm_limit(client_key: str | None = None) -> bool:
    key = _safe_key(client_key)
    r = _get_redis()
    if r is not None:
        try:
            used = int(r.get(f"llm:daily:{_today_key()}:{key}") or 0)
            return used < LLM_DAILY_LIMIT_PER_KEY
        except Exception:
            pass
    _reset_if_new_day()
    mem_key = f"{_today_key()}:{key}"
    return _llm_counters.get(mem_key, 0) < LLM_DAILY_LIMIT_PER_KEY


def increment_llm(client_key: str | None = None) -> int:
    key = _safe_key(client_key)
    r = _get_redis()
    if r is not None:
        try:
            rk = f"llm:daily:{_today_key()}:{key}"
            used = int(r.incr(rk))
            if used == 1:
                r.expire(rk, 86400 + 3600)
            return used
        except Exception:
            pass
    _reset_if_new_day()
    mem_key = f"{_today_key()}:{key}"
    _llm_counters[mem_key] = _llm_counters.get(mem_key, 0) + 1
    return _llm_counters[mem_key]


def get_llm_usage(client_key: str | None = None) -> dict:
    key = _safe_key(client_key)
    r = _get_redis()
    if r is not None:
        try:
            used = int(r.get(f"llm:daily:{_today_key()}:{key}") or 0)
            return {
                "date": _today_key(),
                "used": used,
                "limit": LLM_DAILY_LIMIT_PER_KEY,
                "remaining": max(0, LLM_DAILY_LIMIT_PER_KEY - used),
                "backend": "redis",
                "key": key,
            }
        except Exception:
            pass
    _reset_if_new_day()
    mem_key = f"{_today_key()}:{key}"
    used = _llm_counters.get(mem_key, 0)
    return {
        "date": _today_key(),
        "used": used,
        "limit": LLM_DAILY_LIMIT_PER_KEY,
        "remaining": max(0, LLM_DAILY_LIMIT_PER_KEY - used),
        "backend": "memory",
        "key": key,
    }


def check_api_limit(client_key: str | None = None) -> bool:
    """滑动 1 秒窗口（按客户端键）。"""
    key = _safe_key(client_key)
    r = _get_redis()
    now = time.time()
    if r is not None:
        try:
            rk = f"api:ratelimit:{key}"
            pipe = r.pipeline()
            pipe.zremrangebyscore(rk, 0, now - 1.0)
            pipe.zcard(rk)
            results = pipe.execute()
            return int(results[1]) < API_RATE_PER_SECOND
        except Exception:
            pass
    bucket = _request_timestamps.setdefault(key, [])
    cutoff = now - 1.0
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    return len(bucket) < API_RATE_PER_SECOND


def record_api_call(client_key: str | None = None) -> None:
    key = _safe_key(client_key)
    r = _get_redis()
    now = time.time()
    if r is not None:
        try:
            rk = f"api:ratelimit:{key}"
            member = f"{now:.6f}:{os.getpid()}"
            pipe = r.pipeline()
            pipe.zadd(rk, {member: now})
            pipe.zremrangebyscore(rk, 0, now - 1.0)
            pipe.expire(rk, 2)
            pipe.execute()
            return
        except Exception:
            pass
    _request_timestamps.setdefault(key, []).append(now)


def redis_backend_active() -> bool:
    return _get_redis() is not None


# 向后兼容别名
check_limit = check_llm_limit
increment = increment_llm
