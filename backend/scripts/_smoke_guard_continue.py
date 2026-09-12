import asyncio
from pathlib import Path

from app.db.session import get_async_session_factory
from app.services import assessment, slice_report
from app.services.report_html import build_report_html, try_generate_weasyprint_pdf
from app.services.report_preflight import run_postflight_html, run_preflight
from app.services.report_templates import get_scenario


async def main() -> None:
    Session = get_async_session_factory()
    async with Session() as db:
        all_m = await assessment._ensure_cache(db)
        m = next(x for x in all_m if (x.display_name or "") == "企业48")
        ectx = await slice_report.build_enterprise_report_context(
            db, enterprise_id=m.enterprise_id, report_id="ent48_v"
        )
        pre = run_preflight(ectx)
        print("ent soft", pre.get("soft_flags"), "hard", pre.get("hard_blocks"), "ok", pre["ok"])
        assert pre["ok"]
        assert not pre.get("soft_flags"), pre.get("soft_flags")
        html = build_report_html(ectx, "ent48_v")
        assert "bullet-line" in html
        post = run_postflight_html(html, ectx)
        print("ent post", post["ok"])
        assert post["ok"]
        assert try_generate_weasyprint_pdf(ectx, "ent48_v", Path("/tmp/ent48_v.pdf"))
        spec = get_scenario("tax")
        sctx = await slice_report._build_context_from_spec(
            db, key="tax", spec=spec, industry_l1="批发零售"
        )
        print("tax risks", sctx.get("summary_risks"))
        for r in sctx.get("summary_risks") or []:
            if "家" in r:
                assert "样本" in r, r
        print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
