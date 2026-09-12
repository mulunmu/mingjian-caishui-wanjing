"""切片统计子集契约（公共组件）。

铁律：筛选行业/地区/企业清单后，图表、表格、结论必须同源复用当前子集；
禁止各报告场景各自实现一套「有时过滤、有时复用全集」的逻辑。

所有聚合章节 builder（tax / fraud / signal / financial / …）经 `_load_metrics_scoped`
取数；渲染前由 `validate_scope_sample_alignment` 兜底；PDF 硬门禁拒绝错配。
"""
from __future__ import annotations

import re
from typing import Any

# 低于此阈值：封面/章节必须提示「统计结果仅供参考」
SMALL_SAMPLE_N = 30

# 有筛选时，这些章节的 meta.sample_count 必须 == 当前子集 N
SCOPE_LOCKED_FUNCTIONS = frozenset(
    {"signal", "score", "tax", "authenticity", "fraud", "trend"}
)

# 允许更小子集（如完整三大报表覆盖），但不得大于 scope_n
SCOPE_SUBSET_FUNCTIONS = frozenset({"financial", "benchmark"})

# 「N 家」计数：任意风险主体数不得大于当前子集总样本
_FIRM_COUNT_PATTERNS = (
    re.compile(r"（\s*(\d+)\s*家\s*）"),
    re.compile(r"（\s*(\d+)\s*家\s*/"),
    re.compile(r"(?<![.\d])(\d+)\s*家"),
)


def sample_note(meta: dict[str, Any] | None, *, threshold: int = SMALL_SAMPLE_N) -> str | None:
    """章节统计子集披露文案。"""
    if not meta:
        return None
    n = meta.get("sample_count")
    if not n:
        return None
    n_i = int(n)
    cov = meta.get("financial_coverage")
    if cov is not None and int(cov) != n_i:
        base = f"统计子集 {n_i} 家（其中完整三大报表 {cov} 家）"
    else:
        base = f"统计子集 {n_i} 家"
    if n_i < threshold:
        return f"{base}；样本偏少，统计结果仅供参考"
    return base


def small_sample_banner(sample_count: int | None, *, threshold: int = SMALL_SAMPLE_N) -> str | None:
    """封面/执行摘要级小样本预警（全局开关）。"""
    n = int(sample_count or 0)
    if n <= 0 or n >= threshold:
        return None
    return f"当前统计子集仅 {n} 家，样本有限，统计结果仅供参考，不宜外推为行业整体结论。"


def validate_scope_sample_alignment(
    chapters: list[dict[str, Any]],
    *,
    scope_sample_count: int | None,
    industry_l1: str | None = None,
    province: str | None = None,
    enterprise_ids: list[str] | None = None,
) -> dict[str, Any]:
    """渲染前校验：有筛选时锁定章节样本数必须对齐当前子集。"""
    filtered = bool(industry_l1 or province or enterprise_ids)
    scope_n = int(scope_sample_count or 0)
    mismatches: list[dict[str, Any]] = []
    if not filtered or scope_n <= 0:
        return {"ok": True, "filtered": filtered, "scope_n": scope_n, "mismatches": []}

    for ch in chapters:
        fn = ch.get("function") or ""
        meta = ch.get("meta") or {}
        n = meta.get("sample_count")
        if n is None:
            continue
        n_i = int(n)
        title = ch.get("title") or fn
        if fn in SCOPE_LOCKED_FUNCTIONS and n_i != scope_n:
            mismatches.append(
                {
                    "chapter": title,
                    "function": fn,
                    "chapter_n": n_i,
                    "scope_n": scope_n,
                    "reason": "slice_filter_not_applied",
                }
            )
        elif n_i > scope_n:
            mismatches.append(
                {
                    "chapter": title,
                    "function": fn,
                    "chapter_n": n_i,
                    "scope_n": scope_n,
                    "reason": "chapter_n_exceeds_scope",
                }
            )
    return {
        "ok": len(mismatches) == 0,
        "filtered": filtered,
        "scope_n": scope_n,
        "mismatches": mismatches,
    }


def _extract_firm_counts(text: str) -> list[int]:
    """从展示文案抽取「N 家」整数；同一片段多模式去重取首次命中即可。"""
    t = text or ""
    found: list[int] = []
    seen_spans: set[tuple[int, int]] = set()
    for pat in _FIRM_COUNT_PATTERNS:
        for m in pat.finditer(t):
            span = m.span(1)
            if span in seen_spans:
                continue
            seen_spans.add(span)
            try:
                found.append(int(m.group(1)))
            except (TypeError, ValueError):
                continue
    return found


def validate_firm_counts_within_scope(
    *,
    scope_sample_count: int | None,
    drag_factors: list[dict[str, Any]] | None = None,
    summary_risks: list[str] | None = None,
    summary_strengths: list[str] | None = None,
    texts: list[str] | None = None,
) -> dict[str, Any]:
    """强制校验：风险主体计数（单位「家」）≤ 当前统计子集总样本。

    越界即 ok=False，供 PDF 硬门禁拒绝出报告（禁止「19 家样本写 26 家违法」）。
    """
    scope_n = int(scope_sample_count or 0)
    violations: list[dict[str, Any]] = []
    if scope_n <= 0:
        return {"ok": True, "scope_n": scope_n, "violations": []}

    for f in drag_factors or []:
        cnt = f.get("count")
        item = f.get("item") or ""
        if cnt is None:
            continue
        try:
            n = int(cnt)
        except (TypeError, ValueError):
            continue
        if n > scope_n:
            violations.append(
                {
                    "source": "drag_factors",
                    "item": item,
                    "count": n,
                    "scope_n": scope_n,
                    "reason": "firm_count_exceeds_sample",
                }
            )

    for source, items in (
        ("summary_risks", summary_risks or []),
        ("summary_strengths", summary_strengths or []),
        ("texts", texts or []),
    ):
        for raw in items:
            text = str(raw or "")
            for n in _extract_firm_counts(text):
                if n > scope_n:
                    violations.append(
                        {
                            "source": source,
                            "text": text[:120],
                            "count": n,
                            "scope_n": scope_n,
                            "reason": "firm_count_exceeds_sample",
                        }
                    )

    return {
        "ok": len(violations) == 0,
        "scope_n": scope_n,
        "violations": violations,
    }


def session_cache_compatible(
    *,
    industry_l1: str | None,
    province: str | None,
    enterprise_ids: list[str] | None,
    cached_meta: dict[str, Any] | None,
    scope_sample_count: int | None = None,
) -> bool:
    """会话结论缓存是否可复用于当前切片。

    有行业/地区/企业筛选时，默认禁用会话缓存（避免复用全集 claim 造成切片错配）。
    若缓存 meta.sample_count 已显式等于当前 scope_n，允许复用。
    """
    filtered = bool(industry_l1 or province or enterprise_ids)
    if not filtered:
        return True
    meta = cached_meta or {}
    cached_n = meta.get("sample_count")
    if cached_n is None or scope_sample_count is None:
        return False
    return int(cached_n) == int(scope_sample_count)
