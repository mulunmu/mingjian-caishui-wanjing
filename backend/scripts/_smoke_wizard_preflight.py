"""全场景 × 行业 干跑：扫描 wizard.ok 与 preflight 硬门禁是否同向。

用法（在 backend 目录、DB 可用时）：
  python -m scripts._smoke_wizard_preflight
"""
from __future__ import annotations

import asyncio
import os
import sys

# 干跑关闭 LLM，避免慢与配额
os.environ["LLM_API_KEY"] = ""
os.environ.setdefault("AUTH_REQUIRED", "false")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main() -> int:
    from app.db.session import get_async_session_factory
    from app.services import assessment
    from app.services.report_preflight import run_preflight
    from app.services.report_templates import PORTFOLIO_SCENARIO_KEYS
    from app.services.slice_report import build_slice_report_context, validate_wizard_report

    fac = get_async_session_factory()
    contradictions: list[str] = []
    failures: list[str] = []
    async with fac() as db:
        mets = await assessment._ensure_cache(db)
        industries = sorted({m.industry_l1 for m in mets if m.industry_l1})
        scopes: list[tuple[str | None, str]] = [(None, "全部样本")]
        scopes += [(ind, ind) for ind in industries]

        for scenario in PORTFOLIO_SCENARIO_KEYS:
            for ind, label in scopes:
                wiz = await validate_wizard_report(db, scenario=scenario, industry_l1=ind)
                rid = f"smoke_{scenario}_{(ind or 'all')}"
                try:
                    ctx = await build_slice_report_context(
                        db, scenario=scenario, industry_l1=ind, report_id=rid
                    )
                except Exception as exc:
                    failures.append(f"{scenario}|{label} build_err={exc}")
                    continue
                pf = run_preflight(ctx)
                hard = list(pf.get("hard_blocks") or [])
                # 矛盾：向导通过但硬门禁因 scope/lexicon/firm_count 失败
                gate_hard = set(hard) & {
                    "scope_alignment",
                    "lexicon",
                    "firm_count_guard",
                    "empty_or_no_claims",
                }
                line = (
                    f"{scenario}|{label} wiz={wiz.get('ok')} n={wiz.get('scope_sample_count')} "
                    f"pf={pf.get('ok')} hard={hard}"
                )
                print(line)
                if wiz.get("ok") and gate_hard:
                    contradictions.append(f"{line} WIZARD_PASS_PF_FAIL")
                if not pf.get("ok") and hard:
                    # 记录硬失败（未必是矛盾）
                    failures.append(line)

    print("---")
    print(f"contradictions={len(contradictions)} hard_fail_rows={len(failures)}")
    for c in contradictions:
        print("CONTRADICTION", c)
    return 1 if contradictions else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
