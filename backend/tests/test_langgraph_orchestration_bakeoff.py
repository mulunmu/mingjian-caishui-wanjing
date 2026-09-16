from __future__ import annotations

from pathlib import Path

import pytest

from experiments.langgraph_orchestration_bakeoff import _current_diamond_once


@pytest.mark.asyncio
async def test_current_runtime_bakeoff_diamond_is_deterministic_without_langgraph():
    first = await _current_diamond_once()
    second = await _current_diamond_once()

    assert first[0] == 5
    assert second[0] == 5


def test_langgraph_is_not_a_production_dependency():
    requirements = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(
        encoding="utf-8"
    )
    assert "langgraph" not in requirements.lower()
