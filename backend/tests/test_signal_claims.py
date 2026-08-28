"""风险信号聚合：互斥分桶，避免双计数"""
import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_signal_claims_unique_total_not_sum_of_categories():
    from app.services.judgment_service import build_signal_claims

    m1 = MagicMock(
        enterprise_id="e1",
        revenue_deviation=0.3,
        credit_level="C",
        tax_violation_cnt=1,
        industry_l1="制造",
    )
    m2 = MagicMock(
        enterprise_id="e2",
        revenue_deviation=0.1,
        credit_level="A",
        tax_violation_cnt=0,
        industry_l1="服务",
    )

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [m1, m2]

    class FakeDb:
        async def execute(self, _q):
            return FakeResult()

    claims, meta = await build_signal_claims(FakeDb())  # type: ignore[arg-type]
    total_claim = claims[0]
    # e1 税务违法优先，互斥分桶只计 1；e2 无信号
    assert total_claim.value is not None
    assert total_claim.value.number == 1
    chart = meta["charts"]
    # 仅 1 个行业有信号 → 漏斗图（非热力图）
    assert chart["type"] == "funnel"
    assert chart["data"]["values"][1] == 1
