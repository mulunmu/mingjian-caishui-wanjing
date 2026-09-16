"""Stable, fail-safe percentage selection shared by rollout paths."""
from __future__ import annotations

import hashlib
import math


def stable_bucket(key: str) -> int:
    digest = hashlib.sha256((key or "").encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def normalize_percent(value: int | float | str | None) -> float:
    try:
        percent = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(percent):
        return 0.0
    return max(0.0, min(percent, 100.0))


def is_selected(key: str, percent: int | float | str | None) -> bool:
    value = normalize_percent(percent)
    if value <= 0:
        return False
    if value >= 100:
        return True
    return stable_bucket(key) < value
