"""舞弊引擎：预计算缺失不误报 0/0"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_analyze_metrics_batch_empty_when_precompute_missing():
    from app.services.fraud_engine import analyze_metrics_batch

    rows = [("e1", "样本1", "制造"), ("e2", "样本2", "制造")]
    with patch.dict(os.environ, {"FRAUD_ALLOW_MYSQL_FALLBACK": "false"}):
        with patch("app.services.engine_features_store.load_fraud_features_batch", return_value={}):
            out = analyze_metrics_batch(rows)
    assert out["sample_count"] == 0
    assert out.get("coverage") == "precompute_missing"
    assert out.get("requested_count") == 2


@pytest.mark.asyncio
async def test_build_fraud_claims_precompute_miss_message():
    from unittest.mock import AsyncMock, MagicMock

    from app.services.judgment_service import build_fraud_claims

    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = [("e1", "样本1", "制造")]
    db.execute = AsyncMock(return_value=result)

    miss_out = {
        "industry_l1": "制造",
        "sample_count": 0,
        "precompute_miss": 1,
        "coverage": "precompute_missing",
        "signal_counts": {},
        "avg_composite": 0,
        "flagged_count": 0,
    }
    with patch("app.services.fraud_engine.analyze_metrics_batch", return_value=miss_out):
        with patch("app.services.judgment_service.run_blocking", new_callable=AsyncMock) as rb:
            rb.return_value = miss_out
            claims, meta = await build_fraud_claims(db, "制造")
    assert "预计算" in claims[0].claim
    assert "0/0" not in claims[0].claim
    assert meta.get("coverage") == "precompute_missing"
