from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.core_metrics import CoreMetrics
from app.schemas.semantic_query import QueryType, SemanticQuery
from app.services import extended_metric_executors as executors

from app.services.extended_metric_executors import (
    effective_tax_rate,
    invoice_ratio,
    ocf_to_revenue,
    recency_days,
    top5_share,
)


def test_ratio_returns_none_for_zero_denominator():
    assert invoice_ratio(1, 0) is None
    assert invoice_ratio(None, 10) is None
    assert invoice_ratio(1, 4) == 25.0


def test_ocf_to_revenue_abstains_on_zero_revenue():
    assert ocf_to_revenue(100, 0) is None
    assert ocf_to_revenue(100, 1000) == 10.0


def test_effective_tax_rate_requires_positive_profit():
    assert effective_tax_rate(100, 0) is None
    assert effective_tax_rate(100, -100) is None
    assert effective_tax_rate(100, 1000) == 10.0


def test_top5_share_prefers_json_and_falls_back_to_top1():
    assert top5_share('[{"share":0.2},{"share":0.1}]', 0.05) == 30.0
    assert top5_share("not-json", 0.05) == 5.0
    assert top5_share(None, None) is None


def test_recency_days_uses_latest_event_date():
    today = date(2026, 9, 17)
    assert recency_days([today - timedelta(days=7), today - timedelta(days=20)], today) == 7
    assert recency_days([], today) is None


@pytest.mark.asyncio
async def test_lookup_claim_uses_entity_display_name(monkeypatch):
    async def fake_profile_map(db, ids):
        return {"e1": SimpleNamespace(customer_hhi=Decimal("0.2500"))}

    monkeypatch.setattr(executors, "_profile_map", fake_profile_map)
    row = CoreMetrics(enterprise_id="e1", display_name="企业1", display_label="企业1")
    sq = SemanticQuery(
        query_type=QueryType.lookup,
        metrics=["customer_hhi"],
        entities=["e1"],
    )

    claims, meta = await executors.build_extended_metric_claims(
        object(), sq, "customer_hhi", [row]
    )

    assert claims[0].claim.startswith("企业1")
    assert claims[0].value is not None
    assert claims[0].value.number == 0.25
    assert meta["valid_count"] == 1
