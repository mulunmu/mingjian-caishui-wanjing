"""抗幻觉：报告句中的数字必须能在 claim / value / evidence 中找到锚点"""
from __future__ import annotations

import re
from typing import Any

from app.schemas.claim import Claim, filter_claims
from app.services.scope_contract import (  # 公共切片契约再导出
    SCOPE_LOCKED_FUNCTIONS as _SCOPE_LOCKED_FUNCTIONS,
    validate_firm_counts_within_scope,
    validate_scope_sample_alignment,
)

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


_SENT_SPLIT_RE = re.compile(r"(?<=[。！？；])")


def _split_sentences(text: str) -> list[str]:
    """按中文句末标点切句，去掉空白，供解读段逐句校验（与 llm_reply 同口径）。"""
    return [s.strip() for s in _SENT_SPLIT_RE.split(text or "") if s.strip()]


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


_CHAT_SENT_SPLIT_RE = re.compile(r"(?<=[。！？\n；])")


def _split_chat_sentences(text: str) -> list[str]:
    return [s for s in _CHAT_SENT_SPLIT_RE.split(text or "") if s]


def _filter_followups_by_allowed(followups: list[str], allowed: set[str]) -> list[str]:
    """followups：无数字保留；有数字则必须全部落在 allowed。"""
    out: list[str] = []
    for fu in followups or []:
        nums = [_normalize_num(n) for n in _NUM_RE.findall(fu or "")]
        if not nums or all(n in allowed for n in nums):
            out.append(fu)
    return out


def apply_chat_hallucination_guard(
    reply: str,
    claims: list[Claim] | None,
    *,
    report_hint: str | None = None,
    followups: list[str] | None = None,
) -> tuple[str, str | None, list[str]]:
    """对话终态硬闸门（永不跳过）。

    - 有 allowed 数字：剥离未锚定数字句
    - 无 allowed（无 Claim 或 Claim 无数字）：剥离一切含数字的句子，禁止凭空数字
    返回 (reply, report_hint, followups)。
    """
    kept_claims = filter_claims(claims or [])
    allowed = collect_allowed_numbers(kept_claims) if kept_claims else set()

    def _gate_text(text: str) -> tuple[str, list[str]]:
        parts = _split_chat_sentences(text or "")
        if not parts:
            return (text or "").strip(), []
        if allowed:
            kept_sents, dropped = filter_unanchored_sentences(parts, kept_claims)
        else:
            kept_sents, dropped = [], []
            for s in parts:
                if _NUM_RE.search(s or ""):
                    dropped.append(s)
                else:
                    kept_sents.append(s)
        return "".join(kept_sents).strip(), dropped

    new_reply, dropped_reply = _gate_text(reply or "")
    if dropped_reply:
        pass  # caller may log

    new_hint = report_hint
    if report_hint:
        gated_hint, dropped_hint = _gate_text(report_hint)
        new_hint = gated_hint or None
        if dropped_hint and not dropped_reply:
            dropped_reply = dropped_hint  # signal something was dropped

    fus = list(followups or [])
    if allowed:
        fus = _filter_followups_by_allowed(fus, allowed)
    else:
        fus = [f for f in fus if not _NUM_RE.search(f or "")]

    return new_reply, new_hint, fus


def validate_report_chapters(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    """渲染前校验（claim 唯一化铁律）：除了溯源（asserted/missing_trace），再加两条运行时断言：

    1. 数字锚点——解读段（LLM 润色）里的每个数字必须能在本章 claim/value/evidence 中找到锚点；
    2. 达标↔无风险话术——本章 claim 全达标（无风险结论）时，解读段不得出现风险方向词。

    这两条与 `llm_reply._sanitize_narration` 同源，此处是「渲染前最后一道」兜底：把
    内容层与渲染层的一致性固化成结构化 validation 结果，供前端/API 暴露。
    """
    total_claims = 0
    unanchored = 0
    number_unanchored = 0
    risk_contradictions = 0
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
        # 解读段两条运行时断言（仅针对 LLM 生成的 narration；claim 本体由 builder 条件产出，不在此校验）。
        allowed = collect_allowed_numbers(claims)
        has_risk = claims_have_risk_verdict(claims)
        for sent in _split_sentences(ch.get("narration") or ""):
            if not sentence_has_anchor(sent, allowed):
                number_unanchored += 1
                details.append({"chapter": ch.get("title"), "claim": sent, "reason": "unanchored_number"})
            if not has_risk and sentence_has_risk_direction(sent):
                risk_contradictions += 1
                details.append({"chapter": ch.get("title"), "claim": sent, "reason": "risk_direction_on_clean_chapter"})
    return {
        "ok": unanchored == 0 and number_unanchored == 0 and risk_contradictions == 0 and total_claims > 0,
        "total_claims": total_claims,
        "unanchored": unanchored,
        "number_unanchored": number_unanchored,
        "risk_contradictions": risk_contradictions,
        "empty": total_claims == 0,
        "details": details[:20]
        if total_claims > 0
        else [{"chapter": None, "claim": None, "reason": "empty_report_no_claims"}],
    }


# ── 结论方向约束（claim 唯一化铁律）：全达标章不得出现风险方向话术 ──
# 报告解读段（LLM 润色）只有「数字锚点」校验还不够——LLM 可能用给定数字却给出相反结论
# （如流动比率 1.8 达标却写「偿债承压」）。这里按「章的结论方向」约束措辞：
# 一章的所有 claim 都无风险方向（达标/稳健）时，解读段里出现风险方向词即视为矛盾，丢弃。
_RISK_DIRECTION_WORDS: tuple[str, ...] = (
    "承压", "越线", "跌破", "偏低", "不足", "需核查", "预警",
    "虚开", "可疑", "舞弊", "违例", "异常", "欠税", "滞纳", "困境",
)

# claim 正文命中任一即视为「本章有风险结论」，允许解读段使用风险措辞。
_RISK_VERDICT_MARKERS: tuple[str, ...] = (
    "预警", "虚开", "可疑", "舞弊", "违例", "异常",
    "欠税", "滞纳", "困境", "承压", "越线",
)


def claims_have_risk_verdict(claims: list[Claim]) -> bool:
    """一章的结论是否含风险方向（预警/承压/虚开等）。全达标章返回 False。"""
    for c in filter_claims(claims):
        text = c.claim or ""
        if any(m in text for m in _RISK_VERDICT_MARKERS):
            return True
    return False


def sentence_has_risk_direction(sentence: str) -> bool:
    """单句是否含风险方向话术（承压/越线/预警…）。"""
    return any(w in sentence for w in _RISK_DIRECTION_WORDS)


def _claim_is_renderable(c: Claim) -> bool:
    """可进入 L4 的 claim：非 asserted，且 computed 必须有 trace.table。"""
    if c.confidence == "asserted":
        return False
    if c.confidence == "computed" and (not c.trace or not c.trace.table):
        return False
    return True


def enforce_chapter_integrity(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    """渲染前硬门禁：就地剥离不可溯源 claim，并剔除违规解读句；再交 validate 复检。

    与 validate_report_chapters 同源规则，但这里主动改写 chapters（管道：坏 message 不出文本）。
    """
    dropped_claims = 0
    stripped_sentences = 0
    for ch in chapters:
        raw = ch.get("claims") or []
        kept_claims: list[Any] = []
        claim_objs: list[Claim] = []
        for item in raw:
            c = Claim.model_validate(item) if isinstance(item, dict) else item
            if _claim_is_renderable(c):
                kept_claims.append(item if isinstance(item, dict) else c.model_dump())
                claim_objs.append(c)
            else:
                dropped_claims += 1
        ch["claims"] = kept_claims

        narration = ch.get("narration") or ""
        if not narration:
            continue
        allowed = collect_allowed_numbers(claim_objs)
        has_risk = claims_have_risk_verdict(claim_objs)
        kept_sents: list[str] = []
        for sent in _split_sentences(narration):
            if not sentence_has_anchor(sent, allowed):
                stripped_sentences += 1
                continue
            if not has_risk and sentence_has_risk_direction(sent):
                stripped_sentences += 1
                continue
            kept_sents.append(sent)
        ch["narration"] = "".join(kept_sents) if kept_sents else ""

    return {
        "dropped_claims": dropped_claims,
        "stripped_sentences": stripped_sentences,
    }


def _flatten_chapter_claims(chapters: list[dict[str, Any]]) -> list[Claim]:
    out: list[Claim] = []
    for ch in chapters or []:
        for item in ch.get("claims") or []:
            out.append(Claim.model_validate(item) if isinstance(item, dict) else item)
    return out


def _kpi_is_traced(kpi: dict[str, Any]) -> bool:
    """场景 KPI（metric+source）视为 L0 可回溯；通用聚合卡无 metric 时须对齐 claim。"""
    return bool(kpi.get("metric") and kpi.get("source"))


def collect_surface_allowed_numbers(
    chapters: list[dict[str, Any]],
    summary_kpis: list[dict[str, Any]] | None = None,
) -> set[str]:
    """封面/摘要可用数字 = 章 claim 锚点 ∪ 已溯源 KPI 数值。"""
    allowed = collect_allowed_numbers(_flatten_chapter_claims(chapters))
    for kpi in summary_kpis or []:
        if not _kpi_is_traced(kpi):
            continue
        val = str(kpi.get("value") or "")
        if val in ("—", ""):
            continue
        for n in _NUM_RE.findall(val):
            allowed.add(_normalize_num(n))
    return allowed


def enforce_kpi_claim_alignment(
    summary_kpis: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """无 metric+source 的封面 KPI：数字必须 ⊆ 章 claim 锚点，否则弃权为「—」。"""
    allowed = collect_allowed_numbers(_flatten_chapter_claims(chapters))
    out: list[dict[str, Any]] = []
    blanked = 0
    details: list[dict[str, Any]] = []
    for kpi in summary_kpis or []:
        val = str(kpi.get("value") or "")
        if val in ("—", "") or _kpi_is_traced(kpi):
            out.append(kpi)
            continue
        nums = [_normalize_num(n) for n in _NUM_RE.findall(val)]
        if not nums or all(n in allowed for n in nums):
            out.append(kpi)
            continue
        blanked += 1
        details.append({"label": kpi.get("label"), "value": val, "reason": "kpi_not_in_claims"})
        out.append({**kpi, "value": "—"})
    return out, {"blanked_kpis": blanked, "details": details[:10]}


def enforce_surface_text(text: str, allowed: set[str]) -> tuple[str, int]:
    """剥离表面文本中无数字锚点的句子（story / 执行摘要）。"""
    if not (text or "").strip():
        return text or "", 0
    kept, dropped = [], []
    for s in _split_sentences(text):
        if sentence_has_anchor(s, allowed):
            kept.append(s)
        else:
            dropped.append(s)
    if not kept and dropped:
        return "摘要数字无法与结论对齐，已弃权（不编造）。", len(dropped)
    return "".join(kept), len(dropped)


def validate_cross_surface(
    *,
    chapters: list[dict[str, Any]],
    summary_kpis: list[dict[str, Any]] | None = None,
    story: str = "",
    executive_summary: str = "",
) -> dict[str, Any]:
    """跨面数字机检：无溯源 KPI ⊆ claim；story/执行摘要数字 ⊆ claim∪溯源 KPI。"""
    allowed = collect_surface_allowed_numbers(chapters, summary_kpis)
    claim_allowed = collect_allowed_numbers(_flatten_chapter_claims(chapters))
    details: list[dict[str, Any]] = []
    kpi_unaligned = 0
    text_unanchored = 0

    for kpi in summary_kpis or []:
        val = str(kpi.get("value") or "")
        if val in ("—", "") or _kpi_is_traced(kpi):
            continue
        nums = [_normalize_num(n) for n in _NUM_RE.findall(val)]
        if nums and not all(n in claim_allowed for n in nums):
            kpi_unaligned += 1
            details.append({"surface": "kpi", "text": val, "reason": "kpi_not_in_claims"})

    for surface, text in (("story", story), ("executive_summary", executive_summary)):
        for sent in _split_sentences(text or ""):
            if not sentence_has_anchor(sent, allowed):
                text_unanchored += 1
                details.append({"surface": surface, "text": sent, "reason": "unanchored_number"})

    return {
        "ok": kpi_unaligned == 0 and text_unanchored == 0,
        "kpi_unaligned": kpi_unaligned,
        "text_unanchored": text_unanchored,
        "details": details[:20],
    }


def enforce_cross_surface(
    *,
    chapters: list[dict[str, Any]],
    summary_kpis: list[dict[str, Any]],
    story: str,
    executive_summary: str,
) -> tuple[list[dict[str, Any]], str, str, dict[str, Any]]:
    """就地对齐封面 KPI + 剥离 story/摘要无锚点句；返回改写后的三元组与统计。"""
    aligned_kpis, kpi_stats = enforce_kpi_claim_alignment(summary_kpis, chapters)
    allowed = collect_surface_allowed_numbers(chapters, aligned_kpis)
    new_story, story_stripped = enforce_surface_text(story, allowed)
    new_exec, exec_stripped = enforce_surface_text(executive_summary, allowed)
    stats = {
        **kpi_stats,
        "stripped_story_sentences": story_stripped,
        "stripped_summary_sentences": exec_stripped,
    }
    return aligned_kpis, new_story, new_exec, stats


_TEMPORAL_RE = re.compile(r"(逐年|不断|(?<!可)持续(?!经营))")


def scrub_temporal_words(text: str) -> str:
    """单期场景：去掉时序词（保留「持续经营」）。"""
    if not text:
        return text
    out = text.replace("持续亏损", "亏损")
    out = _TEMPORAL_RE.sub("", out)
    out = re.sub(r"[，,]{2,}", "，", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" ，,")


def validate_radar_subset_of_chapters(
    *,
    radar_dims: list[str] | None,
    chapter_dim_keys: list[str] | None,
) -> dict[str, Any]:
    """铁律：雷达维度 ⊆ 正文章节维度。"""
    radar = set(radar_dims or [])
    chapters = set(chapter_dim_keys or [])
    extra = sorted(radar - chapters)
    return {
        "ok": len(extra) == 0,
        "radar_dims": sorted(radar),
        "chapter_dims": sorted(chapters),
        "extra_in_radar": extra,
    }


def collect_context_surface_texts(context: dict[str, Any]) -> list[tuple[str, str]]:
    """收集报告用户可见面文本（用于禁词 / 字段隔离机检）。"""
    out: list[tuple[str, str]] = []
    for key in ("story", "executive_summary", "title", "subtitle"):
        t = context.get(key)
        if isinstance(t, str) and t.strip():
            out.append((key, t))
    for kpi in context.get("summary_kpis") or []:
        for part in ("label", "value"):
            v = kpi.get(part)
            if isinstance(v, str) and v.strip():
                out.append((f"kpi.{part}", v))
    cover = context.get("cover_meta") or {}
    for k, v in cover.items():
        if isinstance(v, str) and v.strip():
            out.append((f"cover_meta.{k}", v))
    overall = context.get("overall") or {}
    for k in ("health", "risk_level", "outlook", "summary", "reason"):
        v = overall.get(k)
        if isinstance(v, str) and v.strip():
            out.append((f"overall.{k}", v))
    for list_key in ("risk_points", "advantages", "advice"):
        for i, item in enumerate(overall.get(list_key) or []):
            if isinstance(item, str) and item.strip():
                out.append((f"overall.{list_key}[{i}]", item))
    for i, ch in enumerate(context.get("chapters") or []):
        for k in ("title", "narration", "body", "summary"):
            v = ch.get(k)
            if isinstance(v, str) and v.strip():
                out.append((f"chapter[{i}].{k}", v))
        for j, c in enumerate(ch.get("claims") or []):
            if isinstance(c, dict):
                claim = c.get("claim")
            else:
                claim = getattr(c, "claim", None)
            if isinstance(claim, str) and claim.strip():
                out.append((f"chapter[{i}].claim[{j}]", claim))
    return out


def validate_surface_lexicon(
    context: dict[str, Any],
    *,
    report_kind: str = "slice",
) -> dict[str, Any]:
    """规范书禁词 + 聚合字段隔离（硬失败）+ 时序词粗检（仅警告，因缺期数上下文）。"""
    from app.services.report_templates import scan_forbidden_in_text

    hard: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    surfaces = collect_context_surface_texts(context)

    if report_kind == "slice":
        for surf, text in surfaces:
            if "评级展望" in text:
                hard.append({"surface": surf, "hit": "评级展望", "reason": "aggregate_subject_field"})
        for kpi in context.get("summary_kpis") or []:
            label = str(kpi.get("label") or "")
            if label in ("评级展望", "风险等级"):
                hard.append({"surface": "kpi.label", "hit": label, "reason": "aggregate_subject_field"})
        # 聚合不得携带单主体 outlook 字段
        if (context.get("cover_meta") or {}).get("outlook") or (context.get("overall") or {}).get("outlook"):
            hard.append({"surface": "outlook", "hit": "outlook", "reason": "aggregate_subject_field"})

    for surf, text in surfaces:
        for hit in scan_forbidden_in_text(text):
            hard.append({"surface": surf, "hit": hit, "reason": "forbidden_marker"})
        for m in _TEMPORAL_RE.finditer(text):
            warnings.append({"surface": surf, "hit": m.group(0), "reason": "temporal_word"})

    return {
        "ok": len(hard) == 0,
        "hit_count": len(hard),
        "warning_count": len(warnings),
        "details": hard[:40],
        "warnings": warnings[:20],
    }
