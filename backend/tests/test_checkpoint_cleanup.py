from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from scripts.cleanup_langgraph_checkpoints import cleanup_old_threads


def test_checkpoint_cleanup_skips_when_tables_missing():
    report = cleanup_old_threads(create_engine("sqlite:///:memory:"), dry_run=True)
    assert report["ok"] is True
    assert "skipped" in report


def test_checkpoint_cleanup_rejects_unsafe_retention():
    with pytest.raises(ValueError, match="older_than_days"):
        cleanup_old_threads(create_engine("sqlite:///:memory:"), older_than_days=0)
