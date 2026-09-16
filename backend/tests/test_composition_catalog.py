from __future__ import annotations

from app.services.composition_catalog import build_composition_catalog


def test_catalog_exposes_at_least_sixty_modules():
    catalog = build_composition_catalog()
    assert len(catalog) >= 60


def test_catalog_contains_metric_operator_threshold_and_chapter_modules():
    kinds = {module.kind for module in build_composition_catalog().values()}
    assert {"metric", "operator", "threshold", "chapter"} <= kinds


def test_catalog_only_exposes_validated_modules():
    assert all(module.status == "validated" for module in build_composition_catalog().values())
