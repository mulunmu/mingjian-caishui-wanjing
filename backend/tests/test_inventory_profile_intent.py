from __future__ import annotations

import pytest

from app.services.dialog_act import deterministic_inventory_or_profile


@pytest.mark.parametrize(
    ("query", "dimension", "industry", "province"),
    [
        ("有哪些行业？", "industry", None, None),
        ("行业有哪些？", "industry", None, None),
        ("本数据库里有哪些行业？", "industry", None, None),
        ("我能分析哪些行业？他们分别的数量是多少？", "industry", None, None),
        ("有哪些地区？", "province", None, None),
        ("广东省有哪些行业？", "industry", None, "广东"),
        ("制造业有哪些企业？", None, "制造", None),
        ("江苏有哪些企业？", None, None, "江苏"),
        ("制造业的地区分布", "province", "制造", None),
    ],
)
def test_inventory_queries_are_deterministic(
    query: str,
    dimension: str,
    industry: str | None,
    province: str | None,
):
    act = deterministic_inventory_or_profile(query)

    assert act is not None
    assert act.act == "negotiate_scope"
    assert act.inventory_dimension == dimension
    assert act.industry_l1 == industry
    assert act.province == province


def test_subject_profile_query_preserves_subject_reference():
    act = deterministic_inventory_or_profile("企业1的地区和行业是什么？")

    assert act is not None
    assert act.act == "subject_profile"
    assert act.subject_ref == "企业1"
