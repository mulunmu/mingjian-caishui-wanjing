"""Request tracing, lightweight runtime metrics and optional Sentry wiring."""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import Counter, deque
from contextvars import ContextVar, Token
from typing import Any

logger = logging.getLogger(__name__)

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_lock = threading.Lock()
_counters: Counter[str] = Counter()
_latencies: dict[str, deque[float]] = {}
_sentry_initialized = False


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(value: str | None = None) -> tuple[str, Token]:
    trace_id = (value or "").strip() or new_trace_id()
    return trace_id, _trace_id.set(trace_id)


def reset_trace_id(token: Token) -> None:
    _trace_id.reset(token)


def get_trace_id() -> str:
    return _trace_id.get()


def init_sentry() -> bool:
    """Initialize Sentry only when a DSN is explicitly configured."""
    global _sentry_initialized
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            release=os.getenv("APP_RELEASE") or os.getenv("GIT_COMMIT") or None,
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
            send_default_pii=False,
            max_request_body_size="never",
        )
        _sentry_initialized = True
        return True
    except Exception as exc:
        logger.warning("Sentry initialization skipped: %s", exc)
        return False


def sentry_initialized() -> bool:
    return _sentry_initialized


def capture_exception(exc: BaseException) -> None:
    if not _sentry_initialized:
        return
    try:
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("trace_id", get_trace_id())
            sentry_sdk.capture_exception(exc)
    except Exception:
        logger.debug("Sentry capture failed", exc_info=True)


def _metric_key(name: str, tags: dict[str, Any] | None = None) -> str:
    if not tags:
        return name
    suffix = ",".join(f"{key}={value}" for key, value in sorted(tags.items()))
    return f"{name}|{suffix}"


def increment_metric(name: str, tags: dict[str, Any] | None = None, amount: int = 1) -> None:
    key = _metric_key(name, tags)
    with _lock:
        _counters[key] += int(amount)
    try:
        from app.services.cache_service import get_sync_redis

        redis_client = get_sync_redis()
        if redis_client is not None:
            redis_client.incr(f"obs:counter:{key}", int(amount))
    except Exception:
        pass


def observe_latency(name: str, latency_ms: float, tags: dict[str, Any] | None = None) -> None:
    key = _metric_key(name, tags)
    value = max(0.0, float(latency_ms))
    with _lock:
        bucket = _latencies.setdefault(key, deque(maxlen=1000))
        bucket.append(value)
    try:
        from app.services.cache_service import get_sync_redis

        redis_client = get_sync_redis()
        if redis_client is not None:
            redis_key = f"obs:latency:{key}"
            redis_client.zadd(
                redis_key,
                {f"{time.time_ns()}:{uuid.uuid4().hex[:8]}": value},
            )
            redis_client.zremrangebyrank(redis_key, 0, -1001)
            redis_client.expire(redis_key, 86400)
    except Exception:
        pass


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * ratio)))
    return round(ordered[index], 2)


def metrics_snapshot() -> dict[str, Any]:
    with _lock:
        counters = dict(_counters)
        latencies = {key: list(values) for key, values in _latencies.items()}
    try:
        from app.services.cache_service import get_sync_redis

        redis_client = get_sync_redis()
        if redis_client is not None:
            for redis_key in redis_client.scan_iter(match="obs:counter:*", count=200):
                counters[redis_key.removeprefix("obs:counter:")] = int(
                    redis_client.get(redis_key) or 0
                )
            for redis_key in redis_client.scan_iter(match="obs:latency:*", count=200):
                values = [float(value) for value in redis_client.zrange(redis_key, 0, -1)]
                latencies[redis_key.removeprefix("obs:latency:")] = values[-1000:]
    except Exception:
        pass
    latency_summary = {
        key: {
            "count": len(values),
            "p50_ms": _percentile(values, 0.50),
            "p95_ms": _percentile(values, 0.95),
            "max_ms": round(max(values), 2) if values else 0.0,
        }
        for key, values in latencies.items()
    }
    return {
        "trace_id": get_trace_id(),
        "sentry_initialized": _sentry_initialized,
        "counters": counters,
        "latency": latency_summary,
    }


def reset_runtime_metrics() -> None:
    """Test helper: clear process-local counters and latency samples."""
    with _lock:
        _counters.clear()
        _latencies.clear()
