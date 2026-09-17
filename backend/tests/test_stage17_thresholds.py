from __future__ import annotations

from app.services.authenticity_engine import cross_source_deviation


def test_cross_avg_deviation_boundary_is_inclusive():
    below = cross_source_deviation(vat_revenue=100, invoice_revenue=80)
    exact = cross_source_deviation(vat_revenue=100, invoice_revenue=75)
    above = cross_source_deviation(vat_revenue=100, invoice_revenue=70)

    assert round(below["avg_deviation"], 4) == 0.2
    assert below["suspicious"] is False
    assert round(exact["avg_deviation"], 4) == 0.25
    assert exact["suspicious"] is True
    assert round(above["avg_deviation"], 4) == 0.3
    assert above["suspicious"] is True


def test_cross_max_deviation_boundary_is_inclusive():
    below = cross_source_deviation(vat_revenue=100, invoice_revenue=65)
    exact = cross_source_deviation(vat_revenue=100, invoice_revenue=60)
    above = cross_source_deviation(vat_revenue=100, invoice_revenue=55)

    assert round(below["max_deviation"], 4) == 0.35
    assert round(exact["max_deviation"], 4) == 0.4
    assert exact["suspicious"] is True
    assert round(above["max_deviation"], 4) == 0.45
    assert above["suspicious"] is True
