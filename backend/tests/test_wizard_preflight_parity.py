"""向导预校验 vs PDF 硬门禁：禁止「向导通过、生成拒绝」类矛盾。"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_score_overall_respects_industry_filter():
    """制造筛选下 overall 章 sample_count 必须 = 行业子集，禁止回落全库。"""
    pytest.importorskip("asyncpg")
    from app.db.session import get_async_session_factory
    from app.services import assessment
    from app.services.judgment_service import build_score_claims

    fac = get_async_session_factory()
    async with fac() as db:
        all_m = await assessment._ensure_cache(db)
        if not all_m:
            pytest.skip("no live metrics")
        ind = "制造"
        scope_n = sum(1 for m in all_m if m.industry_l1 == ind)
        if scope_n < 5:
            pytest.skip("manufacturing sample too small")
        _claims, meta = await build_score_claims(db, industry_l1=ind, dimension="overall")
        assert int(meta.get("sample_count") or 0) == scope_n


@pytest.mark.asyncio
async def test_portrait_manufacturing_preflight_ok(monkeypatch):
    """制造×画像：scope_alignment / lexicon 不得硬拒。"""
    pytest.importorskip("asyncpg")
    monkeypatch.setenv("LLM_API_KEY", "")  # 跳过 LLM，加速干跑
    from app.db.session import get_async_session_factory
    from app.services import assessment
    from app.services.report_preflight import run_preflight
    from app.services.slice_report import build_slice_report_context, validate_wizard_report

    fac = get_async_session_factory()
    async with fac() as db:
        mets = await assessment._ensure_cache(db)
        n = sum(1 for m in mets if m.industry_l1 == "制造")
        if n < 5:
            pytest.skip("no manufacturing sample")
        wiz = await validate_wizard_report(db, scenario="portrait", industry_l1="制造")
        ctx = await build_slice_report_context(
            db, scenario="portrait", industry_l1="制造", report_id="test_scope_mfg"
        )
        sa = (ctx.get("validation") or {}).get("scope_alignment") or {}
        assert sa.get("ok") is True, sa.get("mismatches")
        pf = run_preflight(ctx)
        hard = set(pf.get("hard_blocks") or [])
        assert "scope_alignment" not in hard, hard
        assert "lexicon" not in hard, (ctx.get("validation") or {}).get("lexicon")
        # 向导与硬门禁同向
        if pf.get("ok"):
            assert wiz.get("ok") is True, wiz
        else:
            # 若仍有其他硬块，向导至少不得对 scope/lexicon 误报通过
            if hard & {"scope_alignment", "lexicon"}:
                assert wiz.get("ok") is False, (wiz, hard)


@pytest.mark.asyncio
async def test_alert_it_software_lexicon_sanitized(monkeypatch):
    """IT软件×预警：claim 表面不得残留禁词，向导与 preflight 同向通过。"""
    pytest.importorskip("asyncpg")
    monkeypatch.setenv("LLM_API_KEY", "")
    from app.db.session import get_async_session_factory
    from app.services import assessment
    from app.services.hallucination_guard import collect_context_surface_texts
    from app.services.report_preflight import run_preflight
    from app.services.slice_report import build_slice_report_context, validate_wizard_report

    fac = get_async_session_factory()
    async with fac() as db:
        mets = await assessment._ensure_cache(db)
        if sum(1 for m in mets if m.industry_l1 == "IT软件") < 1:
            pytest.skip("no IT软件 sample")
        wiz = await validate_wizard_report(db, scenario="alert", industry_l1="IT软件")
        ctx = await build_slice_report_context(
            db, scenario="alert", industry_l1="IT软件", report_id="test_lex_it"
        )
        for _surf, text in collect_context_surface_texts(ctx):
            assert "IT软件" not in text, text[:80]
        pf = run_preflight(ctx)
        assert "lexicon" not in (pf.get("hard_blocks") or []), pf.get("hard_blocks")
        assert wiz.get("ok") is True, wiz
        assert pf.get("ok") is True, pf.get("hard_blocks")
