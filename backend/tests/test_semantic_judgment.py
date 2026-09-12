"""SemanticQuery 执行层：comparison / ranking / distribution / segmentation / correlation。

FakeDb / monkeypatch，仿 test_signal_claims.py；不依赖真实数据库。
"""
import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _row(**kw):
    return MagicMock(**kw)


@pytest.mark.asyncio
async def test_comparison_two_values_and_spread(monkeypatch):
    from app.schemas.semantic_query import CompareTarget, SemanticQuery
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        if province == "广东":
            return [_row(credit_score=80), _row(credit_score=90)]
        if province == "江苏":
            return [_row(credit_score=70)]
        return []

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="comparison",
        metrics=["credit_score"],
        compare=[CompareTarget(dimension="province", values=["广东", "江苏"])],
    )
    claims, meta = await judgment_service.build_comparison_claims(None, sq)  # type: ignore[arg-type]

    values = [c for c in claims if c.value and c.value.metric == "compare_credit_score"]
    assert len(values) == 2
    spread = next(c for c in claims if c.trace and c.trace.query_id == "Q_comparison_spread")
    assert spread.value is None  # 评分类指标不暴露原始分差（业务语言）
    assert "信用表现" in spread.claim
    assert meta["charts"]["type"] == "bar"


@pytest.mark.asyncio
async def test_comparison_province_applies_industry_filter(monkeypatch):
    from app.schemas.semantic_query import CompareTarget, SemanticQuery
    from app.services import judgment_service

    calls: list[tuple] = []

    async def fake_load(db, industry_l1=None, province=None):
        calls.append((industry_l1, province))
        if industry_l1 == "制造":
            if province == "江西":
                return [_row(credit_score=85), _row(credit_score=88)]
            if province == "湖南":
                return [_row(credit_score=80)]
        return []

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="comparison",
        metrics=["credit_score"],
        compare=[CompareTarget(dimension="province", values=["江西", "湖南"])],
        filters={"industry_l1": ["制造"]},
    )
    claims, meta = await judgment_service.build_comparison_claims(None, sq)  # type: ignore[arg-type]

    values = [c for c in claims if c.value and c.value.metric == "compare_credit_score"]
    assert len(values) == 2  # 两省都命中制造业样本
    # 每个省份切片都必须带上 industry_l1=制造（否则 filter 被丢弃，样本退化为全行业）
    assert all(ind == "制造" for ind, _ in calls)


@pytest.mark.asyncio
async def test_comparison_missing_sample_explicit_claim(monkeypatch):
    from app.schemas.semantic_query import CompareTarget, SemanticQuery
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        if province == "江西":
            return [_row(credit_score=85)]
        return []  # 湖南无样本

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="comparison",
        metrics=["credit_score"],
        compare=[CompareTarget(dimension="province", values=["江西", "湖南"])],
    )
    claims, meta = await judgment_service.build_comparison_claims(None, sq)  # type: ignore[arg-type]

    # 有样本的一省正常出 claim
    jiangxi = [c for c in claims if c.value and c.value.metric == "compare_credit_score"]
    assert len(jiangxi) == 1
    assert jiangxi[0].value.number == pytest.approx(85.0)

    # 无样本的一省显式说明，且不带数字、置信度为 inferred
    no_sample = [c for c in claims if "湖南暂无样本" in c.claim]
    assert len(no_sample) == 1
    assert no_sample[0].value is None
    assert no_sample[0].confidence == "inferred"

    # 只有一省有样本 → 不产 spread
    assert not any(c.value and c.value.metric == "compare_spread" for c in claims)


@pytest.mark.asyncio
async def test_segmentation_credit_score_region_dimension(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _row(industry_l1="制造", province="广东", credit_score=90),
            _row(industry_l1="制造", province="江苏", credit_score=70),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="segmentation",
        metrics=["credit_score"],
        dimensions=["province"],  # 按「各地区」拆分
    )
    claims, meta = await judgment_service.build_segmentation_claims(None, sq)  # type: ignore[arg-type]

    texts = [c.claim for c in claims if c.value and c.value.metric == "avg_credit_score"]
    assert texts, "应有地区分组 claim"
    # 维度正确：地区分组而非硬编码行业
    assert all("地区" in t for t in texts)
    assert not any("行业" in t for t in texts)


@pytest.mark.asyncio
async def test_ranking_group_top_n(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery, SortSpec
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _row(industry_l1="制造", credit_score=90),
            _row(industry_l1="制造", credit_score=80),
            _row(industry_l1="服务", credit_score=70),
            _row(industry_l1="建筑", credit_score=60),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="ranking",
        metrics=["credit_score"],
        dimensions=["industry_l1"],
        limit=2,
        sort=SortSpec(metric="credit_score", order="desc"),
    )
    claims, meta = await judgment_service.build_ranking_claims(None, sq)  # type: ignore[arg-type]

    ranks = [c for c in claims if c.value and c.value.metric == "rank_credit_score"]
    assert len(ranks) == 2
    assert ranks[0].value.number == pytest.approx(85.0)
    assert ranks[0].value.number >= ranks[1].value.number
    assert meta["charts"]["type"] == "bar"


@pytest.mark.asyncio
async def test_ranking_ascending_uses_low_ordinal(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery, SortSpec
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _row(industry_l1="制造", credit_score=90),
            _row(industry_l1="服务", credit_score=70),
            _row(industry_l1="建筑", credit_score=60),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="ranking",
        metrics=["credit_score"],
        dimensions=["industry_l1"],
        limit=2,
        sort=SortSpec(metric="credit_score", order="asc"),
    )
    claims, meta = await judgment_service.build_ranking_claims(None, sq)  # type: ignore[arg-type]

    ranks = [c for c in claims if c.value and c.value.metric == "rank_credit_score"]
    assert len(ranks) == 2
    # 升序（最低）措辞用「第 N 低」而非「第 N 名」
    assert "第1低" in ranks[0].claim
    assert ranks[0].value.number == pytest.approx(60.0)
    assert ranks[0].value.number <= ranks[1].value.number


@pytest.mark.asyncio
async def test_ranking_enterprise_anonymized(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services import assessment, judgment_service

    async def fake_list_all(db):
        return [
            {"enterprise_id": "md5hash0001", "display_label": "样本A", "overall_score": 88.0, "risk_level": "高风险"},
            {"enterprise_id": "md5hash0002", "display_label": "样本B", "overall_score": 55.0, "risk_level": "中风险"},
        ]

    monkeypatch.setattr(assessment, "list_all", fake_list_all)

    sq = SemanticQuery(query_type="ranking", metrics=["overall_score"], limit=2)
    claims, meta = await judgment_service.build_ranking_claims(None, sq)  # type: ignore[arg-type]

    ranks = [c for c in claims if c.value and c.value.metric == "rank_overall_score"]
    assert len(ranks) == 2
    # 脱敏：任何 claim 不含真实企业名 / 明文（只出现匿名编号与标签）
    for c in ranks:
        assert "enterprise_name" not in c.claim
        assert "样本A" in c.claim or "样本B" in c.claim


@pytest.mark.asyncio
async def test_distribution_risk_level_pie(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services import assessment, judgment_service

    async def fake_summary(db):
        return {
            "sample_count": 10,
            "high_risk_count": 3,
            "avg_score": 70.0,
            "warning_count": 4,
            "risk_distribution": {"高风险": 3, "中风险": 5, "低风险": 2},
        }

    monkeypatch.setattr(assessment, "get_dashboard_summary", fake_summary)

    sq = SemanticQuery(query_type="distribution", metrics=["risk_level"])
    claims, meta = await judgment_service.build_distribution_claims(None, sq)  # type: ignore[arg-type]

    levels = [c for c in claims if c.value and c.value.metric == "risk_level_count"]
    assert len(levels) == 3
    assert meta["charts"]["type"] == "pie"
    assert meta["charts"]["data"]["labels"] == ["高风险", "中风险", "低风险"]


@pytest.mark.asyncio
async def test_segmentation_authenticity(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services import authenticity_engine, judgment_service

    async def fake_industries(db):
        return ["制造", "服务"]

    async def fake_load(db, industry_l1=None, province=None):
        return [_row(enterprise_id="e1", industry_l1=industry_l1 or "制造", display_label="样本1", revenue_deviation=0.1)]

    def fake_auth(rows, industry_l1=None):
        return {"avg_authenticity_score": 82.5, "sample_count": len(rows)}

    monkeypatch.setattr(judgment_service, "_distinct_industries", fake_industries)
    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)
    monkeypatch.setattr(authenticity_engine, "analyze_authenticity_batch", fake_auth)

    sq = SemanticQuery(query_type="segmentation", metrics=["authenticity_score"])
    claims, meta = await judgment_service.build_segmentation_claims(None, sq)  # type: ignore[arg-type]

    segs = [c for c in claims if c.value and c.value.metric == "seg_authenticity_score"]
    assert len(segs) == 2
    assert segs[0].value.number == pytest.approx(82.5)
    assert meta["charts"]["type"] == "bar"


@pytest.mark.asyncio
async def test_segmentation_fraud(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services import fraud_engine, judgment_service

    async def fake_industries(db):
        return ["制造"]

    async def fake_load(db, industry_l1=None, province=None):
        return [_row(enterprise_id="e1", display_label="样本1", industry_l1="制造")]

    def fake_fraud(tuples, max_n=40):
        return {"avg_composite": 60.0, "sample_count": len(tuples), "flagged_count": 2}

    monkeypatch.setattr(judgment_service, "_distinct_industries", fake_industries)
    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)
    monkeypatch.setattr(fraud_engine, "analyze_metrics_batch", fake_fraud)

    sq = SemanticQuery(query_type="segmentation", metrics=["fraud_composite_score"])
    claims, meta = await judgment_service.build_segmentation_claims(None, sq)  # type: ignore[arg-type]

    segs = [c for c in claims if c.value and c.value.metric == "seg_fraud_composite"]
    assert len(segs) == 1
    assert segs[0].value.number == 2  # 业务语言：报告舞弊迹象主体数，而非原始均分
    assert "进销错配" in segs[0].claim


@pytest.mark.asyncio
async def test_correlation_pearson_in_range(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _row(credit_score=1, revenue_yoy=0.01),
            _row(credit_score=2, revenue_yoy=0.02),
            _row(credit_score=3, revenue_yoy=0.03),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(query_type="correlation", metrics=["credit_score", "revenue_yoy"])
    claims, meta = await judgment_service.build_correlation_claims(None, sq)  # type: ignore[arg-type]

    corr = next(c for c in claims if c.value and c.value.metric == "corr_credit_score_revenue_yoy")
    assert -1.0 <= corr.value.number <= 1.0
    assert corr.value.number == pytest.approx(1.0, abs=1e-3)
    assert meta["charts"]["type"] == "scatter"


@pytest.mark.asyncio
async def test_run_semantic_query_dispatches_comparison(monkeypatch):
    from app.schemas.semantic_query import CompareTarget, SemanticQuery
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        if province == "广东":
            return [_row(credit_score=90)]
        if province == "江苏":
            return [_row(credit_score=80)]
        return []

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="comparison",
        metrics=["credit_score"],
        compare=[CompareTarget(dimension="province", values=["广东", "江苏"])],
    )
    claims, followups, meta = await judgment_service.run_semantic_query(None, sq, "test-dispatch")  # type: ignore[arg-type]

    assert meta["query_type"] == "comparison"
    assert meta["function"] == "benchmark"
    assert any(c.trace and c.trace.query_id == "Q_comparison_spread" for c in claims)
    assert meta["semantic_query"]["query_type"] == "comparison"
    assert len(followups) > 0


def test_pearson_pure():
    from app.services.judgment_service import _pearson

    assert _pearson([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert _pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    # 不足两个点 / 常量列 → 0
    assert _pearson([1], [1]) == 0.0
    assert _pearson([1, 1, 1], [1, 2, 3]) == 0.0


@pytest.mark.asyncio
async def test_generic_simple_avg_customer_concentration_bar(monkeypatch):
    from decimal import Decimal

    from app.schemas.semantic_query import SemanticQuery
    from app.services import judgment_service

    async def fake_load(db, industry_l1=None, province=None):
        return [
            _row(industry_l1="制造", customer_concentration=Decimal("0.30")),
            _row(industry_l1="制造", customer_concentration=Decimal("0.10")),
            _row(industry_l1="服务", customer_concentration=Decimal("0.20")),
        ]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    sq = SemanticQuery(
        query_type="aggregation",
        metrics=["customer_concentration"],
        dimensions=["industry_l1"],
    )
    claims, meta = await judgment_service.build_aggregation_claims(None, sq)  # type: ignore[arg-type]

    # 客户集中度属比率指标：0.30 → 30.0%
    made = next(c for c in claims if c.value and c.value.metric == "customer_concentration")
    assert made.value.number == pytest.approx(20.0)  # (30+10)/2
    assert meta["charts"]["type"] == "bar"
    assert len(meta["charts"]["data"]["labels"]) == 2
