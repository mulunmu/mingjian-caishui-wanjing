"""指标语义层：规范口径字典（阶段二）"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import field_mapping
from app.services.metric_registry import (
    CANONICAL_METRICS,
    SOURCE_FIELDS,
    build_dictionary,
)


def test_canonical_metrics_complete():
    keys = {m["metric_key"] for m in CANONICAL_METRICS}
    assert "overall_score" in keys
    assert len(CANONICAL_METRICS) >= 10
    required = {
        "metric_key", "name", "description", "metric_type",
        "formula", "unit", "grain", "source_fields", "dimensions", "default_filters",
    }
    valid_fields = {sf["field"] for sf in SOURCE_FIELDS}
    for m in CANONICAL_METRICS:
        assert required <= set(m), f"{m['metric_key']} 缺字段"
        for f in m["source_fields"]:
            assert f in valid_fields, f"{m['metric_key']} 引用未知源字段 {f}"


def test_canonical_metrics_cover_five_dimensions():
    dims = {"tax_health_score", "authenticity_score", "industry_score", "legal_score", "finance_score"}
    keys = {m["metric_key"] for m in CANONICAL_METRICS}
    assert dims <= keys


def test_metric_types_valid():
    valid = {"simple", "ratio", "derived", "computed"}
    for m in CANONICAL_METRICS:
        assert m["metric_type"] in valid, m["metric_key"]


def test_build_dictionary_no_pii():
    rec = SimpleNamespace(
        metric_key="credit_score",
        name="纳税信用分",
        description="税务信用评级量化分",
        metric_type="simple",
        formula="credit_score",
        unit="分",
        grain="enterprise",
        source_fields_json='["credit_score"]',
        dimensions_json='["industry_l1"]',
        default_filters_json="{}",
        edge_cases="",
        is_canonical=True,
    )
    d = build_dictionary([rec])
    assert d["version"] == "1.0"
    assert d["metrics"][0]["metric_key"] == "credit_score"
    assert d["source_fields"]
    assert d["dimensions"]
    # 字典只含元数据，不含任何原始数据/主键
    assert "enterprise_id" not in str(d)


def test_field_mapping_aliases_aligned_with_source_fields():
    fields = {sf["field"] for sf in SOURCE_FIELDS}
    for f in field_mapping.FIELD_ALIASES:
        assert f in fields, f"field_mapping 别名 {f} 不在 SOURCE_FIELDS"
