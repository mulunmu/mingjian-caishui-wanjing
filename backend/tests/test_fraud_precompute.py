"""舞弊引擎：预计算缺失不误报 0/0"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_analyze_metrics_batch_empty_when_precompute_missing():
    from app.services.fraud_engine import analyze_metrics_batch

    rows = [("e1", "样本1", "制造", None), ("e2", "样本2", "制造", None)]
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
    result.all.return_value = [("e1", "样本1", "制造", None, None)]
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
    assert "暂未就绪" in claims[0].claim
    assert "0/0" not in claims[0].claim
    assert "暂不评估" in claims[0].claim
    assert meta.get("coverage") == "precompute_missing"


@pytest.mark.asyncio
async def test_build_fraud_claims_signal_uses_subject_unit():
    """舞弊信号表述：signal_counts 是去重主体数，文案「命中 N 家主体」而非「出现 N 次」。"""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.judgment_service import build_fraud_claims

    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = [("e1", "样本1", "制造", None, None)]
    db.execute = AsyncMock(return_value=result)

    out = {
        "industry_l1": "制造",
        "sample_count": 1,
        "flagged_count": 0,
        "signal_counts": {"scbm_mismatch": 1},
        "avg_composite": 60.0,
    }
    with patch("app.services.judgment_service.run_blocking", new_callable=AsyncMock) as rb:
        rb.return_value = out
        claims, meta = await build_fraud_claims(db, "制造")
    sig = next(c for c in claims if c.value and c.value.metric == "signal_count")
    assert "命中 1 家主体" in sig.claim
    assert sig.value.unit == "家"
    assert "出现" not in sig.claim
