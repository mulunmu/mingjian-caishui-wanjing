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


@pytest.mark.asyncio
async def test_signal_multi_hit_overlap_counting():
    """多重风险叠加：按原始信号逐主体计数（非互斥分桶）。"""
    from app.services.judgment_service import build_signal_claims

    m1 = MagicMock(
        enterprise_id="e1",
        revenue_deviation=0.3,
        credit_level="C",
        tax_violation_cnt=1,
        industry_l1="制造",
    )  # 命中 3 类
    m2 = MagicMock(
        enterprise_id="e2",
        revenue_deviation=0.3,
        credit_level="C",
        tax_violation_cnt=0,
        industry_l1="服务",
    )  # 命中 2 类
    m3 = MagicMock(
        enterprise_id="e3",
        revenue_deviation=0.0,
        credit_level="A",
        tax_violation_cnt=0,
        industry_l1="服务",
    )  # 无命中

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return [m1, m2, m3]

    class FakeDb:
        async def execute(self, _q):
            return FakeResult()

    claims, meta = await build_signal_claims(FakeDb())  # type: ignore[arg-type]
    assert meta["multi_hit_ge2"] == 2
    assert meta["multi_hit_ge3"] == 1
    multi = next(c for c in claims if c.value and c.value.metric == "multi_hit_count")
    assert multi.value.number == 2
    assert "≥2 类风险 2 家" in multi.claim
