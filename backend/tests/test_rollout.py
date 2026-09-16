from __future__ import annotations

from app.services.rollout import is_selected, normalize_percent, stable_bucket


def test_stable_bucket_is_deterministic():
    assert stable_bucket("s1") == stable_bucket("s1")
    assert 0 <= stable_bucket("s1") < 100


def test_percent_is_fail_safe():
    assert normalize_percent("invalid") == 0.0
    assert normalize_percent("nan") == 0.0
    assert normalize_percent(-1) == 0.0
    assert normalize_percent(101) == 100.0
    assert is_selected("s1", 0) is False
    assert is_selected("s1", 100) is True
