"""抗幻觉：报告句中的数字必须能在 claim / value / evidence 中找到锚点"""
from __future__ import annotations

import re
from typing import Any

from app.schemas.claim import Claim, filter_claims

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _normalize_num(s: str) -> str:
    try:
        f = float(s)
        if abs(f - int(f)) < 1e-9:
            return str(int(f))
        return f"{f:.4f}".rstrip("0").rstrip(".")
    except ValueError:
        return s


def collect_allowed_numbers(claims: list[Claim]) -> set[str]:
    allowed: set[str] = set()
    for c in filter_claims(claims):
        for n in _NUM_RE.findall(c.claim or ""):
            allowed.add(_normalize_num(n))
        if c.value and c.value.number is not None:
            allowed.add(_normalize_num(str(c.value.number)))
        for e in c.evidence_chain or []:
            for n in _NUM_RE.findall(e):
                allowed.add(_normalize_num(n))
    return allowed


def sentence_has_anchor(text: str, allowed: set[str]) -> bool:
    nums = [_normalize_num(n) for n in _NUM_RE.findall(text or "")]
    if not nums:
        return True
    return all(n in allowed for n in nums)


def filter_unanchored_sentences(sentences: list[str], claims: list[Claim]) -> tuple[list[str], list[str]]:
    """返回 (保留句, 丢弃句)。"""
    allowed = collect_allowed_numbers(claims)
    kept, dropped = [], []
    for s in sentences:
        if sentence_has_anchor(s, allowed):
            kept.append(s)
        else:
            dropped.append(s)
    return kept, dropped


def validate_report_chapters(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    total_claims = 0
    unanchored = 0
    details = []
    for ch in chapters:
        claims = [Claim.model_validate(c) if isinstance(c, dict) else c for c in ch.get("claims") or []]
        total_claims += len(claims)
        for c in claims:
            if c.confidence == "asserted":
                unanchored += 1
                details.append({"chapter": ch.get("title"), "claim": c.claim, "reason": "asserted"})
            elif c.confidence == "computed" and (not c.trace or not c.trace.table):
                unanchored += 1
                details.append({"chapter": ch.get("title"), "claim": c.claim, "reason": "missing_trace"})
    return {
        "ok": unanchored == 0 and total_claims > 0,
        "total_claims": total_claims,
        "unanchored": unanchored,
        "empty": total_claims == 0,
        "details": details[:20]
        if total_claims > 0
        else [{"chapter": None, "claim": None, "reason": "empty_report_no_claims"}],
    }
