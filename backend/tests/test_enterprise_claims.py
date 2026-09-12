"""个体下钻（Phase B）+ 个体深度报告（Phase C）单元测试"""
import asyncio


def _profile():
    return {
        "enterprise_id": "abc123456789",
        "enterprise_name": "企业1",
        "display_name": "企业1",
        "display_label": "Anonymous Sample",
        "credit_level": "B",
        "overall_score": 61.5,
        "risk_level": "中等风险",
        "industry_l1": "制造",
        "province": "广东",
        "dimensions": {
            "tax_health": 60.0,
            "authenticity": 62.0,
            "industry": 55.0,
            "legal": 70.0,
            "finance": 48.0,
        },
        "dimension_details": {
            "tax_health": {"label": "税务健康", "weight": 0.25},
            "authenticity": {"label": "经营真实性", "weight": 0.25},
            "industry": {"label": "行业地位", "weight": 0.20},
            "legal": {"label": "法律合规", "weight": 0.05},
            "finance": {"label": "财务健康", "weight": 0.15},
        },
        "attribution": {
            "dimensions": {
                "tax_health": {
                    "label": "税务健康",
                    "negative": [{"item": "欠税记录", "deduction": 10}],
                }
            },
            "summary": "主要拖累因素：欠税记录。",
        },
        "warning_signals": ["tax_on_time_rate_low"],
    }


def _bench(eid):
    return {
        "enterprise_id": eid,
        "overall_score": 61.5,
        "groups": {
            "industry": {
                "label": "行业", "value": "制造", "rank": 5, "peer_total": 20,
                "percentile": 76.3, "group_mean": 55.0, "deviation": 6.5, "score": 61.5,
            },
            "province": {
                "label": "地区", "value": "广东", "rank": 3, "peer_total": 8,
                "percentile": 62.5, "group_mean": 60.0, "deviation": 1.5, "score": 61.5,
            },
            "scale": {
                "label": "规模", "value": "小微", "rank": 2, "peer_total": 4,
                "percentile": 50.0, "group_mean": 61.5, "deviation": 0.0, "score": 61.5,
            },
        },
    }


def test_build_enterprise_claims(monkeypatch):
    from app.services import assessment, judgment_service

    async def fake_calculate(db, eid):
        return _profile()

    async def fake_bench(db, eid):
        return _bench(eid)

    monkeypatch.setattr(assessment, "calculate", fake_calculate)
    monkeypatch.setattr(assessment, "peer_benchmark", fake_bench)

    claims, meta = asyncio.run(
        judgment_service.build_enterprise_claims(None, "abc123456789")
    )

    assert meta["enterprise_id"] == "abc123456789"
    assert meta["enterprise_label"] == "企业1"
    assert meta["charts"]["type"] == "radar"
    assert any("综合风险等级" in c.claim for c in claims)
    assert any("排名第 5/20" in c.claim for c in claims)
    assert any("预警信号" in c.claim for c in claims)
    # 数字均须有 trace（computed 可溯源）
    for c in claims:
        assert c.confidence != "asserted"
        if c.confidence == "computed":
            assert c.trace and c.trace.table


def test_build_enterprise_claims_not_found(monkeypatch):
    from app.services import assessment, judgment_service

    async def fake_calculate(db, eid):
        return None

    monkeypatch.setattr(assessment, "calculate", fake_calculate)

    claims, meta = asyncio.run(judgment_service.build_enterprise_claims(None, "nope"))
    assert meta["enterprise_id"] == "nope"
    assert any("未找到" in c.claim for c in claims)


def test_enterprise_followups_include_report():
    from app.services.judgment_service import derive_enterprise_followups

    f = derive_enterprise_followups({}, [])
    assert any("报告" in x for x in f)
    assert len(f) == 3


def test_build_enterprise_report_context(monkeypatch):
    from app.services import assessment, judgment_service, llm_reply, slice_report

    async def fake_calculate(db, eid):
        return _profile()

    async def fake_bench(db, eid):
        return _bench(eid)

    monkeypatch.setattr(assessment, "calculate", fake_calculate)
    monkeypatch.setattr(assessment, "peer_benchmark", fake_bench)
    monkeypatch.setattr(llm_reply, "is_llm_configured", lambda: False)

    ctx = asyncio.run(
        slice_report.build_enterprise_report_context(
            None, enterprise_id="abc123456789", report_id=None
        )
    )

    assert ctx["scenario"] == "enterprise"
    assert "企业1" in ctx["title"]
    assert ctx["tier"] == "general"
    assert ctx["scenario_label"] == "企业财务分析报告"
    # 企业基本信息
    assert ctx["subject"]["name"] == "企业1"
    assert ctx["subject"]["short_id"] == "abc12345"
    assert ctx["subject"]["industry_l1"] == "制造"
    assert ctx["subject"]["province"] == "广东"
    # 总体风险评估
    assert ctx["overall"]["risk_level"] == "中等风险"
    assert ctx["overall"]["overall_score"] == 61.5
    assert ctx["overall"]["health"] == "中等"
    assert ctx["overall"]["benchmark_groups"] is not None
    # 分维度风险分析：db=None（无财务报表）→ 弃权不出现（空数据消除，不再写「无数据」占位）
    assert ctx["dimensions"] == []
    # 主要财务数据：无报表 → 弃权不出现
    assert ctx["statements"] is None
    assert ctx["dupont"] is None
    # 真校验（禁止假 ok 占位）：结构含抗幻觉字段
    v = ctx["validation"]
    assert "number_unanchored" in v
    assert "risk_contradictions" in v
    assert "details" in v
    assert v["ok"] is True
    assert v["total_claims"] >= 1
    # A.1：个体封面 story 来自 claim，禁止营销罐装句
    story = ctx.get("story") or ""
    assert "财务体检：先给综合评级" not in story
    assert story  # 有 claim 则必有导语（或弃权句）；本夹具有 overall claim
    assert "综合经营表现" in story or "弃权" in story or "风险" in story
    # 个体路径跨面机检（与切片同口径）
    assert isinstance(v.get("cross_surface"), dict)
    assert v["cross_surface"].get("ok") is True
    assert isinstance(v.get("cross_enforced"), dict)
    assert ctx.get("summary_kpis")
    assert "executive_summary" in ctx


def test_generate_enterprise_report_id_prefix():
    from app.services.slice_report import _SAFE_REPORT_ID

    assert _SAFE_REPORT_ID.match("ent_abc12345_20260827_120000")
