from __future__ import annotations

import pytest

from app.services.analysis_patterns import (
    COMPARISON_BASIS,
    catalog,
    detect_analysis_pattern,
    detect_comparison_basis,
)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("看营收趋势和拐点", "trend"),
        ("行业占比与集中度", "structure"),
        ("指标分布、分箱和长尾", "distribution"),
        ("按利润排名 Top10", "ranking"),
        ("营收总变化是谁贡献的", "contribution"),
        ("利润下滑的根因是什么", "attribution"),
        ("哪些指标异常或突变", "anomaly"),
        ("营收和现金流有没有相关性", "correlation"),
        ("按行业分层并看占比", "composite:stratification+structure"),
        ("和同行行业基准比较", "benchmark"),
        ("如果收入下降10%做敏感性模拟", "scenario"),
        ("从结论下钻到具体期间", "drilldown"),
        ("把结论组装成报告章节", "report"),
    ],
)
def test_registered_analysis_patterns(query: str, expected: str):
    assert detect_analysis_pattern(query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("跟去年同期对比", "yoy"),
        ("比上一期环比怎么样", "mom"),
        ("和同行业公司相比", "peer"),
        ("距目标值还差多少", "target"),
        ("两个群体切片对比", "cohort_slice"),
        ("企业之间相互对比", "entity_pair"),
    ],
)
def test_comparison_basis_is_explicit(query: str, expected: str):
    assert detect_comparison_basis(query) == expected
    assert expected in COMPARISON_BASIS


def test_catalog_keeps_required_data_driven_patterns():
    keys = {item["key"] for item in catalog()}
    assert {
        "trend",
        "structure",
        "distribution",
        "ranking",
        "contribution",
        "attribution",
        "anomaly",
        "correlation",
        "stratification",
        "benchmark",
        "scenario",
        "drilldown",
        "report",
    }.issubset(keys)
