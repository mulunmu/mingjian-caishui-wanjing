#!/usr/bin/env python
"""全场景决策备忘录核验：全库/行业/个体/定制（多章节组合）。

用法（在 backend 目录或容器内）::
    python -m scripts.verify_decision_memo_reports

退出码：0 全过；1 有失败。数字只来自引擎装配的 context，本脚本只断言结构与分轨。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CUSTOM_PRESETS: list[dict[str, Any]] = [
    {"name": "custom_loan_like", "chapters": ["score", "fraud", "authenticity", "benchmark"], "purpose": "能不能放贷？"},
    {"name": "custom_audit_like", "chapters": ["fraud", "authenticity", "tax", "signal"], "purpose": "优先查谁？"},
    {"name": "custom_warn_like", "chapters": ["signal", "fraud", "tax", "authenticity"], "purpose": "风险在哪？"},
    {"name": "custom_rating_like", "chapters": ["score", "trend", "benchmark"], "purpose": "谁可授信？"},
    {"name": "custom_fraud_only", "chapters": ["fraud"], "purpose": "发票舞弊怎么看？"},
    {"name": "custom_fin_tax", "chapters": ["financial", "tax"], "purpose": "财务和税务合不合规？"},
    {"name": "custom_all8", "chapters": ["financial", "tax", "fraud", "authenticity", "signal", "score", "benchmark", "trend"], "purpose": "全面风控怎么排？"},
]


def _fail(msg: str, failures: list[str]) -> None:
    failures.append(msg)
    print(f"  FAIL: {msg}")


def _ok(msg: str) -> None:
    print(f"  OK: {msg}")


def assert_memo_slice(label: str, ctx: dict[str, Any], *, expect_memo: str | None, failures: list[str]) -> None:
    bluf = (ctx.get("summary_conclusion") or ctx.get("executive_summary") or "").strip()
    gq = (ctx.get("governing_question") or "").strip()
    if not bluf:
        _fail(f"{label}: 缺少 BLUF", failures)
    if not gq:
        _fail(f"{label}: 缺少 governing_question", failures)
    if "为什么：" in bluf:
        _fail(f"{label}: BLUF 仍含同质「为什么：」粘贴", failures)
    if expect_memo and ctx.get("memo_scenario") != expect_memo:
        _fail(f"{label}: memo_scenario={ctx.get('memo_scenario')} 期望 {expect_memo}", failures)
    if expect_memo == "loan" and "可批" not in bluf:
        _fail(f"{label}: 放贷 BLUF 应含可批分桶: {bluf[:80]}", failures)
    if expect_memo == "rating" and "可授信" not in bluf:
        _fail(f"{label}: 评级 BLUF 应含可授信: {bluf[:80]}", failures)
    if expect_memo == "warn" and "异常" not in bluf and "信号" not in bluf:
        _fail(f"{label}: 预警 BLUF 应含异常/信号: {bluf[:80]}", failures)
    if expect_memo == "audit" and "优先查" not in bluf:
        _fail(f"{label}: 稽查 BLUF 应含优先查: {bluf[:80]}", failures)
    actions = ctx.get("top_actions") or []
    if not actions:
        _fail(f"{label}: 缺少 top_actions", failures)
    if not (ctx.get("summary_evidence") or ctx.get("summary_risks")):
        _fail(f"{label}: 缺少摘要依据 summary_evidence/summary_risks", failures)
    for i, ch in enumerate(ctx.get("chapters") or []):
        if not ch.get("action_title") and not ch.get("title"):
            _fail(f"{label}: 章节{i} 无 Action Title", failures)
        verdict = ch.get("verdict_paragraph") or ch.get("so_what") or ""
        if not verdict:
            _fail(f"{label}: 章节{i} 无密段 verdict_paragraph", failures)
        topic = ch.get("topic_title") or ""
        at = ch.get("action_title") or ch.get("title") or ""
        if topic and at == topic and any(k in topic for k in ("雷达", "画像", "总览", "趋势")):
            _fail(f"{label}: 章节仍用主题名作 Action Title: {at}", failures)
        if len(at) > 40:
            _fail(f"{label}: 章节标题过长（应短论断）: {at[:50]}", failures)
    spam = 0
    for ch in ctx.get("chapters") or []:
        for row in ch.get("numeric_rows") or []:
            if any("暂无可用数据" in str(c) for c in row):
                spam += 1
    if spam > 8:
        _fail(f"{label}: 关键数字「暂无可用数据」过多 ({spam})", failures)
    _ok(f"{label}: BLUF={bluf[:60]}… | gq={gq}")


async def main() -> int:
    from app.db.session import get_async_session_factory
    from app.services import assessment, slice_report
    from app.schemas.custom_report import CustomReportSpec
    from app.services.custom_report import spec_to_report_spec
    from app.services.report_templates import get_scenario

    failures: list[str] = []
    bluf_by_scene: dict[str, str] = {}
    Session = get_async_session_factory()

    async with Session() as db:
        # ── 四场景 × 全库 ──
        for key in ("loan", "rating", "warn", "audit"):
            label = f"full/{key}"
            print(f"\n== {label} ==")
            try:
                ctx = await slice_report._build_context_from_spec(
                    db, key=key, spec=get_scenario(key), report_id=None
                )
            except Exception as exc:
                _fail(f"{label}: 生成失败 {exc}", failures)
                continue
            assert_memo_slice(label, ctx, expect_memo=key, failures=failures)
            bluf_by_scene[key] = ctx.get("summary_conclusion") or ""

        # 四场景 BLUF 不得撞车
        if len(set(bluf_by_scene.values())) < len(bluf_by_scene):
            _fail(f"全库四场景 BLUF 同质: {bluf_by_scene}", failures)
        else:
            _ok("全库四场景 BLUF 互异")

        # ── 行业切片（制造 × 放贷/稽查）──
        for key in ("loan", "audit"):
            label = f"industry/制造/{key}"
            print(f"\n== {label} ==")
            try:
                ctx = await slice_report._build_context_from_spec(
                    db,
                    key=key,
                    spec=get_scenario(key),
                    industry_l1="制造",
                    report_id=None,
                )
            except Exception as exc:
                _fail(f"{label}: 生成失败 {exc}", failures)
                continue
            assert_memo_slice(label, ctx, expect_memo=key, failures=failures)

        # ── 个体 ──
        print("\n== enterprise ==")
        try:
            rows = await assessment._ensure_cache(db)
            eid = rows[0].enterprise_id if rows else None
            if not eid:
                _fail("enterprise: 无样本", failures)
            else:
                ctx = await slice_report.build_enterprise_report_context(db, enterprise_id=eid)
                if not ctx.get("governing_question"):
                    _fail("enterprise: 缺少 governing_question", failures)
                reason = (ctx.get("overall") or {}).get("reason") or ctx.get("executive_summary") or ""
                if "为什么：" in reason:
                    _fail("enterprise: reason 含同质粘贴", failures)
                if "暂无可用数据" in json.dumps(ctx.get("statements") or {}, ensure_ascii=False):
                    _fail("enterprise: statements 仍含暂无可用数据占位", failures)
                for sec in (ctx.get("six_dimensions") or []) + (ctx.get("dimensions") or []):
                    if not sec.get("action_title") and not sec.get("title"):
                        _fail("enterprise: 分维无 Action Title", failures)
                _ok(f"enterprise: {reason[:70]}…")
        except Exception as exc:
            _fail(f"enterprise: {exc}", failures)

        # ── 定制多组合 ──
        for preset in CUSTOM_PRESETS:
            label = f"custom/{preset['name']}"
            print(f"\n== {label} ==")
            try:
                spec = CustomReportSpec(
                    title=f"核验·{preset['name']}",
                    chapters=list(preset["chapters"]),
                    purpose=preset.get("purpose") or "",
                )
                report_spec = spec_to_report_spec(spec)
                ctx = await slice_report._build_context_from_spec(
                    db, key="custom", spec=report_spec, report_id=None
                )
            except Exception as exc:
                _fail(f"{label}: 生成失败 {exc}", failures)
                continue
            # 定制至少要有 memo 字段与分轨（不强制等于某一场景，但不得空）
            assert_memo_slice(label, ctx, expect_memo=None, failures=failures)
            if not ctx.get("memo_scenario"):
                _fail(f"{label}: memo_scenario 空", failures)

        # 定制行业范围
        label = "custom/制造/fraud+tax"
        print(f"\n== {label} ==")
        try:
            spec = CustomReportSpec(
                title="制造发票税务定制",
                chapters=["fraud", "tax"],
                purpose="制造行业发票和税务怎么查？",
                industry_l1="制造",
            )
            report_spec = spec_to_report_spec(spec)
            ctx = await slice_report._build_context_from_spec(
                db,
                key="custom",
                spec=report_spec,
                industry_l1="制造",
                report_id=None,
            )
            assert_memo_slice(label, ctx, expect_memo=None, failures=failures)
        except Exception as exc:
            _fail(f"{label}: {exc}", failures)

    print("\n==========")
    if failures:
        print(f"FAILED {len(failures)} checks")
        for f in failures:
            print(" -", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
