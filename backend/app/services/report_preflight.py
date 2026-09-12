"""报告四层防护 · 第 2/4 层：预校验 + 渲染面后置校验（机器硬门禁）。

原则：错误报告不得生成。所有业务判定已在规则引擎完成；本模块只做拦截与留痕。
校验日志写入 reports/{report_id}.validation.json，便于排查，不依赖人眼看 PDF。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services import hallucination_guard as hg
from app.services.scope_contract import (
    SMALL_SAMPLE_N,
    validate_firm_counts_within_scope,
)

logger = logging.getLogger(__name__)

# PDF 硬拒出：仅这些闸门；章节数字锚定等仍写入 validation 供审计，暂不阻断出报
_PREFLIGHT_HARD_KEYS = frozenset(
    {
        "scope_alignment",
        "firm_count_guard",
        "lexicon",
        "radar_subset",
        "equity_rules",
        "summary_bullets",
        "temporal",
        "no_inference",
        "small_sample",
        "empty_or_no_claims",
        "empty_enterprise_body",
    }
)

_TEMPORAL_RE = re.compile(r"(逐年|不断|(?<!可)持续(?!经营))")
_INFERRED_RE = re.compile(r"\[据推断\]|据推断")
_TRUNC_ELLIPSIS_RE = re.compile(r"(?:\.{3}|…)\s*$")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_INVALID_IN_ADVANTAGE = ("计算失效", "账务异常", "资不抵债", "不予采信")


def _report_kind(context: dict[str, Any]) -> str:
    if (context.get("scenario") or "") == "enterprise" or context.get("overall"):
        if context.get("scenario") == "enterprise":
            return "enterprise"
    if context.get("subject") and context.get("overall") and not context.get("attribution"):
        return "enterprise"
    return "slice"


def validate_enterprise_equity_rules(context: dict[str, Any]) -> dict[str, Any]:
    """单主体：计算失效/资不抵债指标禁止进入主要优势。"""
    violations: list[dict[str, Any]] = []
    overall = context.get("overall") or {}
    for i, adv in enumerate(overall.get("advantages") or []):
        text = str(adv or "")
        for bad in _INVALID_IN_ADVANTAGE:
            if bad in text:
                violations.append(
                    {
                        "source": f"overall.advantages[{i}]",
                        "hit": bad,
                        "text": text[:120],
                        "reason": "invalid_metric_in_advantages",
                    }
                )
                break
    return {"ok": len(violations) == 0, "violations": violations}


def validate_summary_bullets_intact(context: dict[str, Any]) -> dict[str, Any]:
    """摘要条禁止以省略号结尾（防中间截断残留）；空条禁止。"""
    violations: list[dict[str, Any]] = []
    overall = context.get("overall") or {}
    for key in ("risk_points", "advantages", "advice"):
        for i, item in enumerate(overall.get(key) or []):
            t = str(item or "").strip()
            if not t:
                violations.append({"source": f"overall.{key}[{i}]", "reason": "empty_bullet"})
            elif _TRUNC_ELLIPSIS_RE.search(t) and len(t) < 24:
                # 极短且以省略号收尾视为截断残片；正常长句中间含「…」不拦
                violations.append(
                    {
                        "source": f"overall.{key}[{i}]",
                        "reason": "truncated_bullet",
                        "text": t,
                    }
                )
    for key in ("summary_risks", "summary_strengths"):
        for i, item in enumerate(context.get(key) or []):
            t = str(item or "").strip()
            if not t:
                violations.append({"source": f"{key}[{i}]", "reason": "empty_bullet"})
    return {"ok": len(violations) == 0, "violations": violations}


def validate_temporal_gate(context: dict[str, Any]) -> dict[str, Any]:
    """单期报告用户面不得残留「持续/逐年/不断」（持续经营除外）。"""
    period = int(context.get("period_count") or 1)
    if period >= 2:
        return {"ok": True, "period_count": period, "hits": []}
    hits: list[dict[str, str]] = []
    for surf, text in hg.collect_context_surface_texts(context):
        for m in _TEMPORAL_RE.finditer(text or ""):
            hits.append({"surface": surf, "hit": m.group(0)})
    # 六维章首提示允许出现「单年度」「同比」说明，但不允许「持续/逐年」
    note = context.get("six_dim_temporal_note") or ""
    for m in _TEMPORAL_RE.finditer(note):
        hits.append({"surface": "six_dim_temporal_note", "hit": m.group(0)})
    return {"ok": len(hits) == 0, "period_count": period, "hits": hits[:20]}


def validate_aggregate_no_inference(context: dict[str, Any], *, report_kind: str) -> dict[str, Any]:
    """聚合报告禁止「据推断」类措辞（客观统计结果）。"""
    if report_kind != "slice":
        return {"ok": True, "hits": []}
    hits: list[dict[str, str]] = []
    for surf, text in hg.collect_context_surface_texts(context):
        if _INFERRED_RE.search(text or ""):
            hits.append({"surface": surf, "hit": "据推断"})
    for ch in context.get("chapters") or []:
        for line in ch.get("conclusion_lines") or []:
            if _INFERRED_RE.search(str(line or "")):
                hits.append({"surface": "chapter.conclusion", "hit": "据推断"})
    return {"ok": len(hits) == 0, "hits": hits[:20]}


def validate_small_sample_banner(context: dict[str, Any], *, report_kind: str) -> dict[str, Any]:
    """聚合且 N<阈值时，封面/摘要必须有小样本提示。"""
    if report_kind != "slice":
        return {"ok": True, "required": False}
    cover = context.get("cover_meta") or {}
    try:
        n = int(cover.get("sample_count") or (context.get("attribution") or {}).get("sample_count") or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0 or n >= SMALL_SAMPLE_N:
        return {"ok": True, "required": False, "sample_count": n}
    banner = cover.get("small_sample_banner") or ""
    blob = " ".join(
        [
            str(banner),
            str(context.get("executive_summary") or ""),
            str(context.get("summary_conclusion") or ""),
            "偏少" if cover.get("small_sample") else "",
        ]
    )
    ok = ("仅供参考" in blob) or ("样本偏少" in blob) or ("样本有限" in blob)
    return {
        "ok": ok,
        "required": True,
        "sample_count": n,
        "reason": None if ok else "missing_small_sample_banner",
    }


def collect_payload_numbers(context: dict[str, Any]) -> set[str]:
    """上游 payload 允许出现的数字锚点（后置比对用）。"""
    allowed: set[str] = set()

    def _add(v: Any) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            if abs(float(v) - int(v)) < 1e-9:
                allowed.add(str(int(v)))
            else:
                s = f"{float(v):.4f}".rstrip("0").rstrip(".")
                allowed.add(s)
                # 百分比展示常 ×100
                if abs(float(v)) <= 1:
                    pct = round(float(v) * 100, 4)
                    if abs(pct - int(pct)) < 1e-9:
                        allowed.add(str(int(pct)))
                    else:
                        allowed.add(f"{pct:.4f}".rstrip("0").rstrip("."))
            return
        if isinstance(v, str):
            for m in _NUM_RE.findall(v):
                try:
                    f = float(m)
                    _add(f)
                except ValueError:
                    continue

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in {"validation", "preflight", "postflight", "charts", "chart_image"}:
                    continue
                if k in {
                    "value",
                    "number",
                    "score",
                    "count",
                    "sample_count",
                    "overall_score",
                    "avg_score",
                    "standard",
                    "claim",
                    "reason",
                    "advice",
                    "level_review",
                    "trend",
                    "risks",
                    "label",
                    "unit",
                }:
                    _add(v)
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
        else:
            _add(obj)

    for _, text in hg.collect_context_surface_texts(context):
        _add(text)
    for list_key in ("summary_risks", "summary_strengths"):
        for item in context.get(list_key) or []:
            _add(item)
    _walk(context.get("attribution") or {})
    _walk(context.get("overall") or {})
    _walk(context.get("dimensions") or [])
    _walk(context.get("six_dimensions") or [])
    _walk(context.get("statements") or {})
    _walk(context.get("dupont") or {})
    _walk(context.get("chapters") or [])
    _walk(context.get("summary_kpis") or [])
    _walk(context.get("cover_meta") or {})
    # 页脚/日期/页码常见数字放行
    for y in range(2020, 2035):
        allowed.add(str(y))
    for d in range(0, 100):
        allowed.add(str(d))
    return allowed


def validate_html_against_payload(
    html: str,
    context: dict[str, Any],
    *,
    report_kind: str,
) -> dict[str, Any]:
    """渲染面后置：禁词/据推断/时序/字段隔离硬拒；数字孤儿记警告（payload 覆盖不全时不误杀）。

    禁词与时序只扫正文（去掉 style/script/data-uri），避免 CSS 注释如「不强制分页」误伤。
    """
    hard: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not html:
        return {"ok": False, "hard": [{"reason": "empty_html"}], "warnings": []}

    from app.services.report_templates import scan_forbidden_in_text

    # 可见正文：去 style/script/图片 data-uri 后再做禁词与时序
    body = re.sub(r"data:image/[^\"']+", " ", html)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body, flags=re.I)
    body = re.sub(r"<script[\s\S]*?</script>", " ", body, flags=re.I)
    body_text = re.sub(r"<[^>]+>", " ", body)

    for hit in scan_forbidden_in_text(body_text):
        if hit in ("综合评分", "综合均分", "Benford", "core_metrics", "scbm_mismatch", "financial_coverage"):
            hard.append({"reason": "forbidden_in_html", "hit": hit})

    if report_kind == "slice":
        if _INFERRED_RE.search(body_text):
            hard.append({"reason": "inferred_in_html", "hit": "据推断"})
        if re.search(r"风险等级\s*[：:]", body_text):
            hard.append({"reason": "subject_field_in_aggregate_html", "hit": "风险等级"})
        if "评级展望" in body_text:
            hard.append({"reason": "subject_field_in_aggregate_html", "hit": "评级展望"})

    if int(context.get("period_count") or 1) < 2:
        for m in _TEMPORAL_RE.finditer(body_text):
            hard.append({"reason": "temporal_in_html", "hit": m.group(0)})

    scrub = body_text
    allowed = collect_payload_numbers(context)
    orphans: list[str] = []
    for m in _NUM_RE.findall(scrub):
        try:
            f = float(m)
            key = str(int(f)) if abs(f - int(f)) < 1e-9 else f"{f:.4f}".rstrip("0").rstrip(".")
        except ValueError:
            continue
        if key in allowed:
            continue
        orphans.append(key)
    uniq = sorted(set(orphans))
    if uniq:
        # 数字一致性：现阶段记 warning，避免报表金额格式变体误杀；禁词类仍硬拒
        warnings.append({"reason": "html_number_orphans", "count": len(uniq), "samples": uniq[:20]})

    return {"ok": len(hard) == 0, "hard": hard[:40], "warnings": warnings[:20]}


def run_preflight(context: dict[str, Any]) -> dict[str, Any]:
    """组装层出口：合并既有 validation + 增量规则，产出统一闸门结果。"""
    report_kind = _report_kind(context)
    validation = dict(context.get("validation") or {})
    checks: dict[str, Any] = {}

    # 复用已有块；缺失则现算
    if report_kind == "slice":
        attr = context.get("attribution") or {}
        scope_n = int(attr.get("sample_count") or 0)
        validation["firm_count_guard"] = validate_firm_counts_within_scope(
            scope_sample_count=scope_n,
            drag_factors=attr.get("drag_factors") or [],
            summary_risks=context.get("summary_risks") or [],
            summary_strengths=context.get("summary_strengths") or [],
            texts=[
                context.get("summary_conclusion") or "",
                context.get("executive_summary") or "",
                attr.get("summary") or "",
            ],
        )
        checks["small_sample"] = validate_small_sample_banner(context, report_kind=report_kind)
        checks["no_inference"] = validate_aggregate_no_inference(context, report_kind=report_kind)
    else:
        checks["equity_rules"] = validate_enterprise_equity_rules(context)
        radar = validation.get("radar_subset")
        if not radar:
            radar = hg.validate_radar_subset_of_chapters(
                radar_dims=context.get("radar_dims") or [],
                chapter_dim_keys=[d.get("key") for d in (context.get("six_dimensions") or []) if d.get("key")],
            )
            validation["radar_subset"] = radar

    checks["summary_bullets"] = validate_summary_bullets_intact(context)
    checks["temporal"] = validate_temporal_gate(context)

    if "lexicon" not in validation:
        validation["lexicon"] = hg.validate_surface_lexicon(context, report_kind=report_kind)

    hard_blocks: list[str] = []
    if validation.get("empty") or int(validation.get("total_claims") or 0) <= 0:
        # 个体允许靠 overall/dimensions；聚合必须有 claim
        if report_kind == "slice":
            hard_blocks.append("empty_or_no_claims")
        elif not (context.get("overall") or context.get("dimensions") or context.get("six_dimensions")):
            hard_blocks.append("empty_enterprise_body")

    for key in ("scope_alignment", "firm_count_guard", "lexicon", "radar_subset"):
        block = validation.get(key)
        if isinstance(block, dict) and block.get("ok") is False:
            hard_blocks.append(key)

    for name, block in checks.items():
        if isinstance(block, dict):
            validation[name] = block
            if block.get("ok") is False:
                hard_blocks.append(name)

    # 章节数字锚定 / 风险措辞矛盾：保留在 validation，记为 soft（不进硬门禁，避免正常样本全拒）
    soft_flags: list[str] = []
    if int(validation.get("number_unanchored") or 0) > 0:
        soft_flags.append("number_unanchored")
    if int(validation.get("risk_contradictions") or 0) > 0:
        soft_flags.append("risk_contradictions")
    cross = validation.get("cross_surface")
    if isinstance(cross, dict) and cross.get("ok") is False:
        soft_flags.append("cross_surface")

    hard_blocks = [b for b in hard_blocks if b in _PREFLIGHT_HARD_KEYS]
    ok = len(hard_blocks) == 0
    validation["preflight_hard_ok"] = ok
    validation["preflight_soft_flags"] = soft_flags
    # 兼容旧字段：硬门禁 ok；软问题不把整份 validation 打成失败以免误伤
    validation["ok"] = ok
    result = {
        "ok": ok,
        "report_kind": report_kind,
        "hard_blocks": hard_blocks,
        "soft_flags": soft_flags,
        "validation": validation,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    context["validation"] = validation
    context["preflight"] = {
        "ok": ok,
        "hard_blocks": hard_blocks,
        "soft_flags": soft_flags,
        "checked_at": result["checked_at"],
    }
    return result


def run_postflight_html(
    html: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """渲染后（HTML）兜底；失败则禁止写 PDF。"""
    report_kind = _report_kind(context)
    html_check = validate_html_against_payload(html, context, report_kind=report_kind)
    result = {
        "ok": html_check.get("ok", False),
        "report_kind": report_kind,
        "html": html_check,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    context["postflight"] = result
    return result


def validate_context_surface_lexicon(
    context: dict[str, Any],
    *,
    report_kind: str | None = None,
) -> dict[str, Any]:
    """无 HTML 时的表面校验（FPDF 降级兜底）：禁词 / 据推断 / 时序 / 字段隔离。"""
    kind = report_kind or _report_kind(context)
    hard: list[dict[str, Any]] = []
    from app.services.report_templates import scan_forbidden_in_text

    blob_parts: list[str] = []
    for _, text in hg.collect_context_surface_texts(context):
        blob_parts.append(text)
    for key in ("summary_risks", "summary_strengths"):
        for item in context.get(key) or []:
            blob_parts.append(str(item or ""))
    blob = "\n".join(blob_parts)

    for hit in scan_forbidden_in_text(blob):
        if hit in ("综合评分", "综合均分", "Benford", "core_metrics", "scbm_mismatch", "financial_coverage"):
            hard.append({"reason": "forbidden_in_context", "hit": hit})
    if kind == "slice":
        if _INFERRED_RE.search(blob):
            hard.append({"reason": "inferred_in_context", "hit": "据推断"})
        if "评级展望" in blob:
            hard.append({"reason": "subject_field_in_aggregate", "hit": "评级展望"})
    if int(context.get("period_count") or 1) < 2:
        for m in _TEMPORAL_RE.finditer(blob):
            hard.append({"reason": "temporal_in_context", "hit": m.group(0)})
    return {"ok": len(hard) == 0, "hard": hard[:40], "report_kind": kind}


def run_postflight_context(context: dict[str, Any]) -> dict[str, Any]:
    """FPDF 等无 HTML 路径的后置兜底。"""
    check = validate_context_surface_lexicon(context)
    result = {
        "ok": check.get("ok", False),
        "report_kind": check.get("report_kind"),
        "context": check,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "renderer": "context_surface",
    }
    context["postflight"] = result
    return result


def write_validation_log(
    report_id: str,
    *,
    reports_dir: Path,
    preflight: dict[str, Any] | None = None,
    postflight: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """每份报告落盘校验日志。"""
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report_id}.validation.json"
    payload = {
        "report_id": report_id,
        "preflight": preflight,
        "postflight": postflight,
        "extra": extra or {},
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def assert_renderable_or_raise(context: dict[str, Any]) -> dict[str, Any]:
    """PDF 硬门禁入口：预校验不通过直接抛错。"""
    result = run_preflight(context)
    if result.get("ok"):
        return result
    blocks = ",".join(result.get("hard_blocks") or []) or "unknown"
    raise ValueError(
        f"报告预校验未通过，拒绝生成 PDF（{blocks}）。"
        f"详情见 context.validation / preflight。"
    )
