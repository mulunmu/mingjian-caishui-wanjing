"""地区评分对比：图表与「最高/最低」结论图文一致（不截断 top8）+ 分母标注。"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _row(province: str, credit_score: float) -> MagicMock:
    return MagicMock(enterprise_id=f"e-{province}", province=province, credit_score=credit_score)


@pytest.mark.asyncio
async def test_region_chart_includes_bottom_province(monkeypatch):
    """图表须展示全部地区（含末位），否则「最高/最低」对比结论引用的末位地区不出现在图中。"""
    from app.services import judgment_service

    provs = [
        ("广东", 92.0), ("江苏", 88.0), ("四川", 85.0), ("上海", 82.0),
        ("山东", 80.0), ("浙江", 78.0), ("陕西", 75.0), ("重庆", 72.0),
        ("江西", 70.0), ("宁波", 61.0), ("内蒙古", 55.0),
    ]

    async def fake_load(db, industry_l1=None, province=None):
        return [_row(p, s) for p, s in provs]

    monkeypatch.setattr(judgment_service, "_load_metrics", fake_load)

    claims, meta = await judgment_service.build_score_claims(None, None, dimension="region")

    labels = meta["charts"]["data"]["labels"]
    # 全部 11 个地区都在图中，末位「内蒙古」可见 → 图文一致
    assert len(labels) == len(provs)
    assert "内蒙古" in labels
    # 分母标注（图表副标题/章节子集披露依赖 meta.sample_count）
    assert meta["sample_count"] == len(provs)
    # 极差结论引用最高与最低
    spread = next(c for c in claims if c.value and c.value.metric == "avg_credit_score_spread")
    assert "广东" in spread.claim and "内蒙古" in spread.claim
