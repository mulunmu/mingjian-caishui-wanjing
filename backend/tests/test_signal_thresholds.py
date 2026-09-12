"""风险信号阈值唯一源：营收偏差 25%/30% 散落已收编，锁定三层一致性。"""
import sys
import os
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_revenue_deviation_threshold_single_source():
    """阈值与标签只此一处定义（曾散落 25%/30%/20%）。"""
    from app.services.metric_registry import REVENUE_DEVIATION_WARN, revenue_deviation_warn_label

    assert REVENUE_DEVIATION_WARN == 0.30
    assert revenue_deviation_warn_label() == "营收偏差≥30%"


def test_revenue_deviation_label_used_by_charts():
    """图表图例与正文标签同源，不再出现「≥25%」与「30%」两处写死。"""
    from app.services.chart_payloads import SIGNAL_X_LABELS
    from app.services.metric_registry import revenue_deviation_warn_label

    assert SIGNAL_X_LABELS[1] == revenue_deviation_warn_label()


def test_insight_a01_uses_unified_threshold():
    """洞察 A-01 边界：0.28 不触发、0.31 触发（与信号分桶同一阈值）。"""
    from app.services.insight_engine import _r_a01_deviation

    assert _r_a01_deviation(MagicMock(revenue_deviation=Decimal("0.28")), None) is None
    assert _r_a01_deviation(MagicMock(revenue_deviation=Decimal("0.31")), None) is not None


def test_warning_signal_uses_unified_threshold():
    """预警信号 revenue_deviation_high 边界：与洞察/分桶同一阈值。"""
    from app.services.assessment import _warning_signals

    def _m(dev: Decimal) -> MagicMock:
        return MagicMock(
            tax_on_time_rate=Decimal("0.95"),
            invoice_monthly_avg=100,
            credit_level="A",
            social_trend="稳定",
            revenue_deviation=dev,
            is_dishonesty=False,
            is_execution=False,
        )

    assert "revenue_deviation_high" not in _warning_signals(_m(Decimal("0.28")), [], 100)
    assert "revenue_deviation_high" in _warning_signals(_m(Decimal("0.31")), [], 100)


@pytest.mark.asyncio
async def test_signal_bucket_uses_unified_threshold():
    """风险信号分桶 high_dev 边界：0.28 不计入、0.31 计入。"""
    from app.services.judgment_service import build_signal_claims

    def _make_row(dev: Decimal) -> MagicMock:
        return MagicMock(
            enterprise_id="e1",
            revenue_deviation=dev,
            credit_level="A",
            tax_violation_cnt=0,
            industry_l1="制造",
        )

    class _FakeResult:
        def __init__(self, dev: Decimal):
            self._dev = dev

        def scalars(self):
            return self

        def all(self):
            return [_make_row(self._dev)]

    class _FakeDb:
        def __init__(self, dev: Decimal):
            self._dev = dev

        async def execute(self, _q):
            return _FakeResult(self._dev)

    _, meta_low = await build_signal_claims(_FakeDb(Decimal("0.28")))  # type: ignore[arg-type]
    assert meta_low["high_dev"] == 0

    _, meta_high = await build_signal_claims(_FakeDb(Decimal("0.31")))  # type: ignore[arg-type]
    assert meta_high["high_dev"] == 1
