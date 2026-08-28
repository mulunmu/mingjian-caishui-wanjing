"""个体画像 + 同业基准定位测试"""
import asyncio


def test_group_position_ranking():
    """多样本分组：排名 / 百分位 / 偏离度正确"""
    from app.services.assessment import _group_position

    r = _group_position([60.0, 70.0, 80.0, 90.0], 80.0, "行业", "制造")
    assert r["rank"] == 2  # 只有 90 高于 80
    assert r["percentile"] == 66.7  # (3-1)/(4-1)*100
    assert r["peer_total"] == 4
    assert r["group_mean"] == 75.0
    assert r["deviation"] == 5.0


def test_group_position_top_and_bottom():
    """最高分 rank=1/百分位=100；最低分 rank=n/百分位=0"""
    from app.services.assessment import _group_position

    top = _group_position([60.0, 70.0, 80.0, 90.0], 90.0, "地区", "广东")
    assert top["rank"] == 1
    assert top["percentile"] == 100.0

    bottom = _group_position([60.0, 70.0, 80.0, 90.0], 60.0, "地区", "广东")
    assert bottom["rank"] == 4
    assert bottom["percentile"] == 0.0


def test_group_position_single_or_empty():
    """单样本 / 空群体：返回中性默认，不除零"""
    from app.services.assessment import _group_position

    single = _group_position([75.0], 75.0, "规模", "小微")
    assert single["peer_total"] == 1
    assert single["percentile"] == 50.0
    assert single["deviation"] == 0.0

    empty = _group_position([], 75.0, "规模", "小微")
    assert empty["peer_total"] == 0
    assert empty["percentile"] == 50.0


def _make_metric(eid: str, industry: str, province: str, scale: str):
    from app.models.core_metrics import CoreMetrics

    return CoreMetrics(
        enterprise_id=eid,
        display_label=f"{province}·{industry}·{scale}",
        industry_l1=industry,
        industry_l2="其他",
        province=province,
        city="测试市",
        scale_label=scale,
    )


def test_peer_benchmark_groups(monkeypatch):
    """peer_benchmark 按行业 / 地区 / 规模三组返回定位（mock 缓存与评估）"""
    from app.services import assessment

    metrics = [
        _make_metric("e0", "制造", "广东", "小微"),
        _make_metric("e1", "制造", "广东", "中坚"),
        _make_metric("e2", "制造", "浙江", "小微"),
        _make_metric("e3", "批发", "广东", "小微"),
    ]
    scores = {"e0": 80.0, "e1": 70.0, "e2": 60.0, "e3": 90.0}

    async def fake_ensure_cache(db):
        return metrics

    def fake_build(m, all_metrics):
        return {"enterprise_id": m.enterprise_id, "overall_score": scores[m.enterprise_id]}

    monkeypatch.setattr(assessment, "_ensure_cache", fake_ensure_cache)
    monkeypatch.setattr(assessment, "_build_from_cache", fake_build)

    result = asyncio.run(assessment.peer_benchmark(None, "e0"))

    assert result["enterprise_id"] == "e0"
    assert result["overall_score"] == 80.0

    # 行业「制造」共 3 家（e0/e1/e2），e0 最高 → rank 1
    industry = result["groups"]["industry"]
    assert industry["peer_total"] == 3
    assert industry["rank"] == 1
    assert industry["value"] == "制造"

    # 地区「广东」共 3 家（e0/e1/e3），e0 次高 → rank 2
    province = result["groups"]["province"]
    assert province["peer_total"] == 3
    assert province["rank"] == 2

    # 规模「小微」共 3 家（e0/e2/e3），e0 次高 → rank 2
    scale = result["groups"]["scale"]
    assert scale["peer_total"] == 3
    assert scale["rank"] == 2


def test_peer_benchmark_unknown(monkeypatch):
    """未知企业返回 None"""
    from app.services import assessment

    async def fake_ensure_cache(db):
        return [_make_metric("e0", "制造", "广东", "小微")]

    monkeypatch.setattr(assessment, "_ensure_cache", fake_ensure_cache)

    result = asyncio.run(assessment.peer_benchmark(None, "nope"))
    assert result is None
