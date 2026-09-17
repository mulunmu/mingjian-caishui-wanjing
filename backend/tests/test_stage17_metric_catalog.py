from __future__ import annotations

from app.services.metric_catalog_v2 import P0_CANDIDATES
from app.models.core_metrics import CoreMetrics
from app.services.metric_registry import CANONICAL_METRICS
from app.services.stage17_metric_catalog import (
    CROSS_DEVIATION_METRICS,
    SUPPORTED_EXTENDED_METRICS,
    UNSUPPORTED_METRICS,
)


def _planned_keys() -> set[str]:
    implemented = {item["metric_key"] for item in CANONICAL_METRICS}
    implemented |= set(CoreMetrics.__table__.columns.keys())
    return {item["metric_key"] for item in P0_CANDIDATES} - implemented


def test_stage17_catalog_classifies_every_p0_candidate_once():
    planned = _planned_keys()
    supported = set(SUPPORTED_EXTENDED_METRICS)
    unsupported = set(UNSUPPORTED_METRICS)

    assert supported.isdisjoint(unsupported)
    assert supported | unsupported == planned


def test_stage17_supported_metrics_have_required_metadata():
    for key, spec in SUPPORTED_EXTENDED_METRICS.items():
        assert spec.metric_key == key
        assert spec.name
        assert spec.formula
        assert spec.source_tables
        assert spec.source_fields
        assert spec.aliases
        assert spec.unit is not None


def test_stage17_unsupported_metrics_have_specific_reasons():
    for key, spec in UNSUPPORTED_METRICS.items():
        assert spec.metric_key == key
        assert len(spec.reason.strip()) >= 8
        assert spec.missing_source


def test_cross_deviation_metrics_are_not_duplicated_in_p0_catalog():
    planned = _planned_keys()
    assert set(CROSS_DEVIATION_METRICS).isdisjoint(planned)
    assert set(CROSS_DEVIATION_METRICS) == {"cross_avg_deviation", "cross_max_deviation"}
