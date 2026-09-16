from __future__ import annotations

from scripts.audit_metric_catalog import build_metric_catalog_audit


def test_audit_identifies_core_metrics_missing_as_retrieval_tools():
    audit = build_metric_catalog_audit()
    missing = set(audit["missing_from_canonical"])
    assert {"debt_ratio", "cash_flow_level", "tax_arrears_cnt"} <= missing


def test_audit_defines_a_p0_catalog_with_complete_field_metadata():
    audit = build_metric_catalog_audit()
    p0 = audit["p0_candidates"]
    assert len(p0) >= 40
    assert all(item["metric_key"] for item in p0)
    assert all(item["formula"] for item in p0)
    assert all(item["source_tables"] for item in p0)
    assert all(item["aliases"] for item in p0)


def test_audit_reports_priority_buckets():
    audit = build_metric_catalog_audit()
    assert audit["counts"]["core_columns"] >= 50
    assert audit["counts"]["canonical_metrics"] >= 20
    assert audit["counts"]["p0_candidates"] >= 40
