"""回归：定制 IT 行业标题 lexicon + 企业2 后置时序不得被 CSS 误伤。"""
from __future__ import annotations

import pytest
from app.services.report_templates import sanitize_surface_industry_terms, scope_label
from app.services.report_preflight import validate_html_against_payload


def test_sanitize_it_software_industry_term():
    assert "IT软件" not in sanitize_surface_industry_terms("IT软件行业发票舞弊风控报告")
    assert "软件信息" in sanitize_surface_industry_terms("IT软件行业发票舞弊")
    assert scope_label("IT软件", None) == "软件信息"


def test_postflight_ignores_css_comment_buduan():
    html = """
    <html><head><style>
    /* 默认不断页；仅自然分页 */
    .x { color: red; }
    </style></head><body><p>红冲占比偏高，需核查。</p></body></html>
    """
    out = validate_html_against_payload(html, {"period_count": 1}, report_kind="enterprise")
    assert out["ok"] is True
    assert not any(h.get("hit") == "不断" for h in out.get("hard") or [])


@pytest.mark.asyncio
async def test_enterprise2_and_it_custom_generate(live_db):
    """活库冒烟：有库才跑；验证企业生成与 IT 定制不再因 lexicon/CSS 拒出。"""
    from sqlalchemy import select

    from app.models.core_metrics import CoreMetrics
    from app.schemas.custom_report import CustomReportSpec
    from app.services.slice_report import generate_custom_report, generate_enterprise_report

    async with live_db() as db:
        e2 = (
            await db.execute(select(CoreMetrics).where(CoreMetrics.display_name == "企业2"))
        ).scalar_one_or_none()
        if e2 is None:
            pytest.skip("no 企业2 in live db")
        rid, path, _ = await generate_enterprise_report(db, e2.enterprise_id, owner="test@local")
        assert rid.startswith("ent_")
        assert path.exists()

        inds = (await db.execute(select(CoreMetrics.industry_l1).distinct())).scalars().all()
        if "IT软件" not in inds:
            pytest.skip("no IT软件 industry")
        spec = CustomReportSpec(
            chapters=["fraud"],
            industry_l1="IT软件",
            title="IT软件行业发票舞弊风控报告",
            purpose="红冲金额占比过高",
        )
        rid2, path2, ctx = await generate_custom_report(
            db, spec=spec, owner="test@local", industry_l1="IT软件"
        )
        assert rid2.startswith("slice_")
        assert path2.exists()
        assert "IT软件" not in (ctx.get("title") or "")
