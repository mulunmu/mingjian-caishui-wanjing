"""上线前全方位报告验收：多场景 × 多轮 × HTML/PDF/向导/禁词/字段隔离。

用法:
  python scripts/_spec_audit_reports.py
环境变量:
  SPEC_AUDIT_ROUNDS=3
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.services import hallucination_guard as hg
from app.services.custom_report import CustomReportSpec
from app.services.report_html import build_report_html
from app.services.report_templates import scan_forbidden_in_text
from app.services.slice_report import (
    REPORTS_DIR,
    generate_custom_report,
    generate_enterprise_report,
    generate_slice_report,
    validate_wizard_report,
)

SCENARIOS = ("financial", "tax", "fraud", "due_diligence", "profile", "overview")
ROUNDS = int(os.environ.get("SPEC_AUDIT_ROUNDS", "3"))
RULE_RE = re.compile(r"\b[TARIF]-\d{2}\b")
TEMPORAL_RE = re.compile(r"(逐年|不断|(?<!可)持续(?!经营))")
_LATIN = re.compile(r"\b[A-Za-z][A-Za-z0-9_\-]{2,}\b")
_ALLOW = re.compile(
    r"^(PDF|KPI|API|ID|OK|N/?A|YoY|VAT|DuPont|CSS|HTML|PNG|SVG|—|-|[A-D]|M)$",
    re.I,
)


def _walk_user_strings(obj: Any, path: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        keys = {
            "title",
            "subtitle",
            "story",
            "purpose",
            "claim",
            "narration",
            "executive_summary",
            "summary_conclusion",
            "label",
            "reason",
            "advice",
            "level_review",
            "trend",
            "outlook",
            "health",
            "risk_level",
            "scenario_label",
            "conclusion",
            "description",
            "value",
        }
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k == "validation" or p.startswith("validation."):
                continue
            if k in keys and isinstance(v, str) and v.strip():
                out.append((p, v))
            elif k in ("risk_points", "advantages", "advice", "summary_strengths", "summary_risks") and isinstance(
                v, list
            ):
                for i, item in enumerate(v):
                    if isinstance(item, str) and item.strip():
                        out.append((f"{p}[{i}]", item))
                    elif isinstance(item, dict):
                        out.extend(_walk_user_strings(item, f"{p}[{i}]"))
            else:
                out.extend(_walk_user_strings(v, p))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            out.extend(_walk_user_strings(item, f"{path}[{i}]"))
    return out


def _audit_html(ctx: dict[str, Any], report_id: str, kind: str) -> list[str]:
    """渲染 HTML 再扫封面标签 / 禁词（与 PDF 同源模板）。"""
    fails: list[str] = []
    try:
        html = build_report_html(ctx, report_id)
    except Exception as exc:
        return [f"html_render:{exc}"]
    if kind != "enterprise":
        if "群体风险判断" not in html:
            fails.append("html_missing_cohort_label")
        # 封面元数据行不得出现「风险等级：」（单主体字段）
        if re.search(r"风险等级\s*[：:]", html):
            fails.append("html_cover_risk_level_label")
        if "评级展望" in html:
            fails.append("html_outlook")
    else:
        if "风险等级" not in html:
            fails.append("html_missing_subject_risk")
    for hit in scan_forbidden_in_text(html):
        # HTML 可能含 class/CSS；仅拦明显业务禁词（综合评分等）
        if hit in ("综合评分", "综合均分", "Benford", "core_metrics", "scbm_mismatch"):
            fails.append(f"html_forbidden:{hit}")
            break
    if RULE_RE.search(html):
        fails.append("html_rule_id")
    return fails


def _audit_one(report_id: str, ctx: dict[str, Any], kind: str, key: str) -> dict[str, Any]:
    val = ctx.get("validation") or {}
    cross = val.get("cross_surface") or {}
    lexicon = val.get("lexicon") or hg.validate_surface_lexicon(
        ctx, report_kind="enterprise" if kind == "enterprise" else "slice"
    )
    story = (ctx.get("story") or "").strip()
    surfaces = _walk_user_strings(ctx)
    blob = "\n".join(t for _, t in surfaces)

    forbidden = sorted(set(scan_forbidden_in_text(blob) + RULE_RE.findall(blob)))
    english: list[dict[str, str]] = []
    for path, text_s in surfaces:
        if ".metric" in path or ".trace" in path or ".source" in path:
            continue
        for tok in _LATIN.findall(text_s):
            if _ALLOW.match(tok):
                continue
            english.append({"path": path, "token": tok, "snippet": text_s[:80]})
    seen: set[tuple[str, str]] = set()
    eng_u: list[dict[str, str]] = []
    for e in english:
        k2 = (e["path"], e["token"])
        if k2 in seen:
            continue
        seen.add(k2)
        eng_u.append(e)

    temporal = sorted({m.group(0) for m in TEMPORAL_RE.finditer(blob)})
    aggregate_bad: list[str] = []
    if kind != "enterprise":
        if "评级展望" in blob:
            aggregate_bad.append("评级展望")
        for kpi in ctx.get("summary_kpis") or []:
            if kpi.get("label") in ("风险等级", "评级展望"):
                aggregate_bad.append(f"kpi:{kpi.get('label')}")

    html_fails = _audit_html(ctx, report_id, kind)

    # P0：英文蛇形字段 / 健康状况 / 雷达对齐
    snake = re.findall(r"\b[a-z]+(?:_[a-z0-9]+)+\b", blob)
    snake = [s for s in snake if s not in ("risk_level", "overall_score", "sample_count")]  # 内部路径偶发
    # 用户面 blob 不应含 financial_coverage 等
    for bad in ("financial_coverage", "current_ratio", "quick_ratio", "scbm_mismatch"):
        if bad in blob:
            hard_fail_pre = True
            break
    else:
        hard_fail_pre = False

    hard_fail: list[str] = []
    if hard_fail_pre or any(x in blob for x in ("financial_coverage", "current_ratio", "quick_ratio")):
        hard_fail.append("english_field")
    if kind != "enterprise" and "健康状况" in blob:
        hard_fail.append("health_field")  # 聚合不应有；个体摘要也不应有
    if kind == "enterprise" and "健康状况" in blob:
        hard_fail.append("health_field")
    radar_check = (val.get("radar_subset") or {})
    if kind == "enterprise" and radar_check and radar_check.get("ok") is False:
        hard_fail.append("radar_subset")
    # 时序：单期硬失败若仍含持续（持续经营除外）
    if int(ctx.get("period_count") or 1) < 2:
        if TEMPORAL_RE.search(blob):
            hard_fail.append("temporal")
    pdf = Path(REPORTS_DIR) / f"{report_id}.pdf"
    pdf_ok = pdf.exists() and pdf.stat().st_size > 2000
    if not pdf_ok:
        hard_fail.append("pdf")
    if not story and kind != "enterprise":
        hard_fail.append("empty_story")
    if val.get("empty") or int(val.get("total_claims") or 0) <= 0:
        if kind == "enterprise":
            if not (ctx.get("dimensions") or ctx.get("overall")):
                hard_fail.append("no_body")
        else:
            hard_fail.append("no_claims")
    if cross and cross.get("ok") is not True:
        hard_fail.append("cross_surface")
    if lexicon and lexicon.get("ok") is not True:
        hard_fail.append("lexicon")
    if forbidden:
        hard_fail.append("forbidden")
    if aggregate_bad:
        hard_fail.append("aggregate_field")
    if eng_u:
        hard_fail.append("english")
    if html_fails:
        hard_fail.extend(html_fails)

    return {
        "report_id": report_id,
        "kind": kind,
        "key": key,
        "scenario": ctx.get("scenario"),
        "title": ctx.get("title"),
        "pdf_ok": pdf_ok,
        "pdf_bytes": pdf.stat().st_size if pdf.exists() else 0,
        "story_preview": story[:120],
        "total_claims": val.get("total_claims"),
        "validation_ok": val.get("ok"),
        "cross_ok": cross.get("ok"),
        "lexicon_ok": lexicon.get("ok"),
        "lexicon_details": (lexicon.get("details") or [])[:8],
        "forbidden_hits": forbidden[:20],
        "english_hits": eng_u[:15],
        "temporal_hits": temporal[:10],
        "aggregate_bad": aggregate_bad,
        "html_fails": html_fails,
        "hard_fail": hard_fail,
        "ok": not hard_fail,
    }


def _fail_row(key: str, exc: Exception) -> dict[str, Any]:
    return {
        "report_id": None,
        "kind": "error",
        "key": key,
        "ok": False,
        "hard_fail": [f"generate_error:{exc}"],
        "forbidden_hits": [],
        "english_hits": [],
    }


async def _safe_slice(db, *, key: str, owner: str, **kwargs) -> dict[str, Any]:
    try:
        rid, _, ctx = await generate_slice_report(db, owner=owner, **kwargs)
        return _audit_one(rid, ctx, "slice", key)
    except Exception as exc:
        return _fail_row(key, exc)


async def _safe_custom(db, *, key: str, owner: str, spec: CustomReportSpec, **kwargs) -> dict[str, Any]:
    try:
        rid, _, ctx = await generate_custom_report(db, spec=spec, owner=owner, **kwargs)
        return _audit_one(rid, ctx, "custom", key)
    except Exception as exc:
        return _fail_row(key, exc)


async def _safe_enterprise(db, *, key: str, owner: str, enterprise_id: str) -> dict[str, Any]:
    try:
        rid, _, ctx = await generate_enterprise_report(db, enterprise_id, owner=owner)
        return _audit_one(rid, ctx, "enterprise", key)
    except Exception as exc:
        return _fail_row(key, exc)


async def _wizard_checks(db: AsyncSession) -> list[dict[str, Any]]:
    """向导预校验：正例应可生成；空切片/坏组合应拦截。"""
    rows: list[dict[str, Any]] = []

    async def one(name: str, expect_ok: bool, **kwargs) -> None:
        try:
            res = await validate_wizard_report(db, **kwargs)
            ok_flag = bool(res.get("ok"))
            passed = ok_flag is expect_ok
            rows.append(
                {
                    "report_id": None,
                    "kind": "wizard",
                    "key": name,
                    "ok": passed,
                    "hard_fail": [] if passed else [f"expect_ok={expect_ok} got={ok_flag} detail={res}"],
                    "wizard": {k: res.get(k) for k in ("ok", "reason", "sample_count", "warnings") if k in res or True},
                }
            )
        except Exception as exc:
            rows.append(_fail_row(name, exc))

    await one("wizard_ok_financial", True, scenario="financial")
    await one("wizard_ok_due", True, scenario="due_diligence", industry_l1="制造")
    await one("wizard_fail_empty_industry", False, scenario="financial", industry_l1="不存在的行业XYZ")
    return rows


async def _run_round(
    db: AsyncSession,
    round_idx: int,
    enterprise_ids: list[str],
    industries: list[str],
    provinces: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    owner = f"launch_audit_r{round_idx}"

    for sc in SCENARIOS:
        results.append(await _safe_slice(db, key=sc, owner=owner, scenario=sc))

    # 行业 / 地区切片
    for ind in industries[:3]:
        results.append(
            await _safe_slice(
                db,
                key=f"due_diligence:{ind}",
                owner=owner,
                scenario="due_diligence",
                industry_l1=ind,
            )
        )
    for prov in provinces[:2]:
        results.append(
            await _safe_slice(
                db,
                key=f"tax:{prov}",
                owner=owner,
                scenario="tax",
                province=prov,
            )
        )

    # 定制组合（标题必须中文，避免验收脚本自身引入拉丁词误报）
    customs = [
        ("custom:fin+tax+fraud", ["financial", "tax", "fraud"], "定制三章·财务税务发票"),
        ("custom:profile+tax", ["profile", "tax"], "定制二章·画像与税务"),
        ("custom:fin+fraud", ["financial", "fraud"], "定制二章·财务与发票"),
    ]
    for key, chapters, title in customs:
        results.append(
            await _safe_custom(
                db,
                key=key,
                owner=owner,
                spec=CustomReportSpec(chapters=chapters, title=title, purpose="上线验收抽查"),
            )
        )

    # 多企业个体
    for i, eid in enumerate(enterprise_ids[:3]):
        results.append(
            await _safe_enterprise(db, key=f"enterprise:{i}:{eid[:8]}", owner=owner, enterprise_id=eid)
        )

    if round_idx == 1:
        results.extend(await _wizard_checks(db))

    return results


async def main() -> None:
    url = os.environ["DATABASE_URL"]
    engine = create_async_engine(url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    all_rows: list[dict[str, Any]] = []

    async with Session() as db:
        inds = [
            str(r[0])
            for r in (
                await db.execute(
                    text(
                        "SELECT industry_l1 FROM core_metrics "
                        "WHERE industry_l1 IS NOT NULL AND industry_l1 <> '' "
                        "GROUP BY industry_l1 ORDER BY COUNT(*) DESC LIMIT 5"
                    )
                )
            ).all()
        ]
        provs = [
            str(r[0])
            for r in (
                await db.execute(
                    text(
                        "SELECT province FROM core_metrics "
                        "WHERE province IS NOT NULL AND province <> '' "
                        "GROUP BY province ORDER BY COUNT(*) DESC LIMIT 3"
                    )
                )
            ).all()
        ]
        eids = [
            str(r[0])
            for r in (
                await db.execute(text("SELECT enterprise_id FROM core_metrics ORDER BY enterprise_id LIMIT 1"))
            ).all()
        ]
        eids += [
            str(r[0])
            for r in (
                await db.execute(
                    text("SELECT enterprise_id FROM core_metrics ORDER BY enterprise_id DESC LIMIT 1")
                )
            ).all()
        ]
        eids += [
            str(r[0])
            for r in (
                await db.execute(text("SELECT enterprise_id FROM core_metrics OFFSET 50 LIMIT 1"))
            ).all()
        ]
        # 去重保序
        seen_e: set[str] = set()
        enterprise_ids: list[str] = []
        for e in eids:
            if e not in seen_e:
                seen_e.add(e)
                enterprise_ids.append(e)
        if not enterprise_ids:
            raise RuntimeError("no enterprise in core_metrics")

        print(
            f"audit plan: rounds={ROUNDS} industries={inds} provinces={provs} ents={len(enterprise_ids)}",
            flush=True,
        )
        for r in range(1, ROUNDS + 1):
            print(f"=== ROUND {r}/{ROUNDS} ===", flush=True)
            rows = await _run_round(db, r, enterprise_ids, inds, provs)
            all_rows.extend(rows)
            for row in rows:
                status = "PASS" if row.get("ok") else "FAIL"
                print(
                    f"[{status}] {row.get('key')} {row.get('report_id')} "
                    f"fail={row.get('hard_fail')} forbid={row.get('forbidden_hits')}",
                    flush=True,
                )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rounds": ROUNDS,
        "total": len(all_rows),
        "passed": sum(1 for x in all_rows if x.get("ok")),
        "failed": sum(1 for x in all_rows if not x.get("ok")),
        "fail_keys": [x.get("key") for x in all_rows if not x.get("ok")],
        "rows": all_rows,
    }
    path = Path(REPORTS_DIR) / "_spec_audit_launch.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {path} passed={out['passed']}/{out['total']} fail_keys={out['fail_keys']}", flush=True)
    await engine.dispose()
    raise SystemExit(0 if out["failed"] == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
