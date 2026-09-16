from __future__ import annotations

import pytest

from scripts.run_staging_canary_smoke import _validate_case


def test_canary_smoke_accepts_primary_claims_without_canary_metadata():
    result = _validate_case(
        {"name": "analysis", "expect_canary": True},
        {
            "reply": "primary answer",
            "data": {
                "primary": {"status": "answered", "fallback": False},
                "claims": [{"metric": "debt_ratio"}],
            },
        },
        {"messages": [{"role": "assistant", "content": "primary answer"}]},
    )
    assert result["primary_status"] == "answered"
    assert result["primary_fallback"] is False


def test_canary_smoke_rejects_primary_fallback():
    with pytest.raises(AssertionError, match="fallback=True"):
        _validate_case(
            {"name": "analysis", "expect_canary": True},
            {
                "reply": "fallback answer",
                "data": {
                    "primary": {"status": "answered", "fallback": True},
                    "claims": [{"metric": "debt_ratio"}],
                },
            },
            {"messages": [{"role": "assistant", "content": "fallback answer"}]},
        )
