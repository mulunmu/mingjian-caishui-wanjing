"""P1-1: tax_violation 与 high_severity 不得全额双扣。"""

from app.services.assessment import _tax_violation_deductions


def test_equal_counts_use_base_plus_premium_not_35n():
    items = _tax_violation_deductions(2, 2)
    total = sum(i["deduction"] for i in items)
    # 旧逻辑: 2*15 + 2*20 = 70；新逻辑: 2*15 + 2*5 = 40
    assert total == 40
    assert any(i["item"] == "税务违法" for i in items)
    assert any(i["item"] == "高危事件加成" for i in items)
    assert not any(i["item"] == "高危事件" and i["deduction"] == 40 for i in items)


def test_high_is_subset_of_viol():
    items = _tax_violation_deductions(3, 1)
    assert sum(i["deduction"] for i in items) == 3 * 15 + 1 * 5


def test_orphan_high_without_viol():
    items = _tax_violation_deductions(0, 2)
    assert sum(i["deduction"] for i in items) == 40


def test_high_exceeds_viol_orphan_remainder():
    items = _tax_violation_deductions(1, 3)
    # 1*15 + 1*5 + 2*20 = 60
    assert sum(i["deduction"] for i in items) == 60


def test_zero():
    assert _tax_violation_deductions(0, 0) == []
