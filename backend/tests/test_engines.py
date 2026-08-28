"""阶段3验收：反欺诈进销错配 + Benford 违例"""
from app.services.fraud_engine import (
    fake_mismatch_sample,
    scbm_mismatch_score,
    detect_sequence_mismatches,
    analyze_invoice_bundle,
)
from app.services.authenticity_engine import (
    fake_benford_violation_sample,
    natural_benford_sample,
    benford_test,
    cross_source_deviation,
)


def test_scbm_mismatch_flags_fake_sample():
    result = fake_mismatch_sample()
    assert "scbm_mismatch" in result["signals"]
    assert result["scbm_mismatch"]["signal"] is True
    assert result["scbm_mismatch"]["score"] > 50
    assert result["confidence"] == "computed"
    assert result["composite_score"] > 40


def test_scbm_match_low_score():
    r = scbm_mismatch_score(["1080", "1081", "1070"], ["1080", "1081"])
    assert r["signal"] is False
    assert r["orphan_sell_ratio"] == 0.0


def test_scbm_trader_buy_many_sell_few_not_flagged():
    """进多销少的贸易样本：销项类目均在进项内，不应误报。"""
    buy = ["1010", "1030", "1040", "1050", "1060", "1070", "1080", "1090"] * 20
    sell = ["1080", "1090"] * 10
    r = scbm_mismatch_score(buy, sell)
    assert r["signal"] is False
    assert r["orphan_sell_ratio"] == 0.0


def test_sequence_gap_detection():
    # 局部跳号 102→110（缺 7 号）应计入；跨票本巨跳不应拉高 gap_ratio
    r = detect_sequence_mismatches(["100", "101", "102", "110", "111"])
    assert r["gap_count"] == 7
    assert r["local_gap_events"] == 1
    assert r["sample_size"] == 5
    assert 0 < r["gap_ratio"] <= 0.5


def test_sequence_ignores_cross_book_jumps():
    r = detect_sequence_mismatches(["100", "101", "99999999"])
    assert r["local_gap_events"] == 0
    assert r["batch_jumps"] == 1
    assert r["gap_ratio"] == 0.0


def test_benford_violation_sample():
    r = fake_benford_violation_sample()
    assert r["violation"] is True
    assert r["conformity"] == "nonconformity"
    assert r["mad"] is not None and r["mad"] > 0.015
    assert r["confidence"] == "computed"


def test_benford_natural_sample_not_flagged_harshly():
    r = natural_benford_sample()
    assert r["n"] >= 50
    # 自然对数均匀分布应接近符合，至少不应是不足样本
    assert r["conformity"] != "insufficient_sample"


def test_cross_source_suspicious():
    r = cross_source_deviation(
        vat_revenue=1_000_000,
        invoice_revenue=1_050_000,
        finance_revenue=2_800_000,
    )
    assert r["suspicious"] is True
    assert r["avg_deviation"] > 0.2


def test_cross_source_consistent():
    r = cross_source_deviation(
        vat_revenue=1_000_000,
        invoice_revenue=1_020_000,
        finance_revenue=980_000,
    )
    assert r["suspicious"] is False


def test_analyze_bundle_trace_present():
    r = analyze_invoice_bundle(
        buy_scbm=["1080"],
        sell_scbm=["3040"],
        red_cnt=1,
        invoice_cnt=50,
        amounts_by_counterparty=[100, 100, 100],
    )
    assert "trace" in r
    assert "syx_invoice" in r["trace"]["tables"]
