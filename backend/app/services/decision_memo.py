"""决策备忘录层：把「风险画像」收成「决策答案」。

根因：报告按数据维度组织 → 四场景摘要同质化、章节松散复读。
本模块是共享决策链（slice / custom / enterprise 共用）：

1. governing_question — 本报告只回答一个问题
2. BLUF — 摘要「判断」一句（分场景分轨，禁止 risks[0] 粘贴）
3. 依据 — 摘要默认全文可见（风险数字），不折叠
4. 优先处置 — ≤3 条可执行动作
5. 章节 — 短论断标题 + 密段（判断+依据+处置），禁止「论断/所以呢」分栏
6. 白话 — 只改表达，不编数字（铁律）

数字只来自 attribution / chapters / risk_distribution；此处不调用引擎重算。
"""
from __future__ import annotations

import re
from typing import Any

from app.services.plain_language import translate_terms
from app.services.report_templates import (
    PORTFOLIO_AUDIT_CHAPTERS,
    PORTFOLIO_LOAN_CHAPTERS,
    PORTFOLIO_PORTRAIT_CHAPTERS,
    PORTFOLIO_ALERT_CHAPTERS,
    actionable_advice,
    chapter_conclusion_lines,
    strip_bullet_prefix,
)

# ── 每个场景只回答一个问题 ──────────────────────────────────────────
GOVERNING_QUESTIONS: dict[str, str] = {
    "loan": "能不能放贷？附加什么条件？",
    "rating": "群体信用结构？谁可授信？",
    "warn": "风险在哪？哪些企业该预警？",
    "audit": "哪些可疑？优先查谁？查什么？",
    "enterprise": "这家值不值得做？先盯什么？",
    "custom": "本组数据说明了什么？下一步该做什么？",
}

# 放贷分桶：可批 / 附加条件 / 不建议（对齐 assessment.RISK_LEVELS 标签）
_APPROVE = frozenset({"低风险"})
_CONDITIONAL = frozenset({"中低风险", "中等风险"})
_REJECT = frozenset({"中高风险", "高风险"})

_CONFIDENCE_LABELS = {
    "high": "置信较高",
    "medium": "置信中等",
    "low": "样本偏少，仅供参考",
}

# 空处置 / 口水动作：禁止进入报告
_EMPTY_ACTION_RE = re.compile(
    r"对照关键数字核对|留下可复核记录|详见正文|建议：对照|见结论与可照做"
)


def resolve_memo_scenario(
    key: str | None,
    chapters: list[dict[str, Any]] | None = None,
    *,
    purpose: str | None = None,
) -> str:
    """归一到 loan|rating|warn|audit|enterprise|custom 的决策口径。

    定制报告：按章节功能集合推断最接近的决策问题，避免退回「画像总结」同质句。
    """
    k = (key or "").strip().lower()
    if k == "enterprise":
        return "enterprise"
    if k in GOVERNING_QUESTIONS and k != "custom":
        # 旧 key 由调用方先 _canonical；此处再收一次
        from app.services.report_templates import _canonical

        c = _canonical(k)
        if c in ("loan", "rating", "warn", "audit"):
            return c

    funcs = {str(ch.get("function") or "") for ch in (chapters or [])}
    ordered = [str(ch.get("function") or "") for ch in (chapters or []) if ch.get("function")]
    if not funcs and purpose:
        from app.services.plain_language import detect_scenario

        d = detect_scenario(purpose)
        return d if d != "general" else "custom"

    # 章节集合 → 场景（定制自由组合的根映射；顺序优先于集合）
    if funcs and funcs <= PORTFOLIO_LOAN_CHAPTERS and {"fraud", "authenticity", "benchmark"} <= funcs:
        return "loan"
    if ordered and ordered[0] == "signal":
        return "warn"
    if ordered and ordered[0] in ("fraud", "authenticity") and funcs <= (
        PORTFOLIO_AUDIT_CHAPTERS | PORTFOLIO_ALERT_CHAPTERS
    ):
        return "audit"
    if funcs and funcs <= PORTFOLIO_ALERT_CHAPTERS:
        # 预警与稽查章节集合相同：有真实性交叉 → 稽查；信号打头/主导 → 预警
        if "authenticity" in funcs and "fraud" in funcs:
            return "audit"
        if "signal" in funcs:
            return "warn"
        if "fraud" in funcs:
            return "audit"
        return "warn"
    if funcs and funcs <= PORTFOLIO_PORTRAIT_CHAPTERS:
        return "rating"
    if funcs & {"fraud", "authenticity"} and not (funcs & {"trend", "benchmark"}):
        if "signal" in funcs or "tax" in funcs:
            return "audit" if ("fraud" in funcs and "authenticity" in funcs) else "warn"
    if funcs & {"fraud", "authenticity", "tax"} and "benchmark" not in funcs:
        return "audit" if "fraud" in funcs and "authenticity" in funcs else "warn"
    if funcs & {"score", "trend", "benchmark"} and not (funcs & {"fraud", "signal"}):
        return "rating"
    if "fraud" in funcs and "authenticity" in funcs and "benchmark" in funcs:
        return "loan"
    return "custom"


def governing_question(
    key: str | None,
    chapters: list[dict[str, Any]] | None = None,
    *,
    purpose: str | None = None,
) -> str:
    memo = resolve_memo_scenario(key, chapters, purpose=purpose)
    if memo == "custom" and purpose:
        p = purpose.strip()
        if p.endswith("？") or p.endswith("?"):
            return p
        return f"{p.rstrip('。')}？下一步该做什么？"
    return GOVERNING_QUESTIONS.get(memo, GOVERNING_QUESTIONS["custom"])


def risk_buckets(distribution: dict[str, int] | None) -> dict[str, int]:
    """风险等级分布 → 放贷三桶。"""
    dist = distribution or {}
    approve = sum(int(dist.get(k) or 0) for k in _APPROVE)
    conditional = sum(int(dist.get(k) or 0) for k in _CONDITIONAL)
    reject = sum(int(dist.get(k) or 0) for k in _REJECT)
    # 未知标签并入附加条件，避免 silently drop
    known = approve + conditional + reject
    total = sum(int(v or 0) for v in dist.values())
    if total > known:
        conditional += total - known
    return {"approve": approve, "conditional": conditional, "reject": reject, "total": total}


def _top_cluster(
    industry_dist: dict[str, int] | None,
    province_dist: dict[str, int] | None,
    *,
    limit: int = 2,
) -> str:
    parts: list[str] = []
    if industry_dist:
        top_i = sorted(industry_dist.items(), key=lambda kv: -int(kv[1] or 0))[:limit]
        parts.extend(translate_terms(str(k)) for k, _ in top_i if k)
    if province_dist and len(parts) < limit:
        top_p = sorted(province_dist.items(), key=lambda kv: -int(kv[1] or 0))[: limit - len(parts)]
        parts.extend(str(k) for k, _ in top_p if k)
    return "、".join(parts) if parts else ""


def _primary_blockers(
    attribution: dict[str, Any] | None,
    risks: list[str] | None,
    *,
    limit: int = 2,
) -> list[str]:
    """主要卡点：优先拖累因素，其次摘要风险句（白话、短标签）。"""
    out: list[str] = []
    seen: set[str] = set()
    for d in (attribution or {}).get("drag_factors") or []:
        item = translate_terms(str(d.get("item") or "").strip())
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            return out
    for r in risks or []:
        short = translate_terms(strip_bullet_prefix(r))
        short = re.split(r"[，。；（(]", short)[0].strip()
        # 去掉「N 家」尾巴，留卡点名
        short = re.sub(r"\d+\s*家.*$", "", short).strip(" ：:")
        if not short or short in seen:
            continue
        seen.add(short)
        out.append(short)
        if len(out) >= limit:
            break
    return out


def _score_to_risk_level(score: float) -> str:
    from app.services import assessment

    for threshold, label in assessment.RISK_LEVELS:
        if score >= threshold:
            return label
    return "高风险"


def confidence_tag(sample_count: int, *, small_n: int = 30) -> dict[str, str]:
    if sample_count <= 0:
        return {"level": "low", "label": _CONFIDENCE_LABELS["low"]}
    if sample_count < small_n:
        return {"level": "low", "label": _CONFIDENCE_LABELS["low"]}
    if sample_count < 80:
        return {"level": "medium", "label": _CONFIDENCE_LABELS["medium"]}
    return {"level": "high", "label": _CONFIDENCE_LABELS["high"]}


def _top_signal_labels(chapters: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    """从 signal/fraud 章提炼 Top 异常短标签（白话、去「结论：」前缀与英文键）。"""
    from app.services.report_templates import ZH_SIGNAL_LABELS

    labels: list[str] = []
    seen: set[str] = set()

    def _clean(raw: str) -> str:
        short = translate_terms(strip_bullet_prefix(raw))
        short = re.sub(r"^结论[:：]\s*", "", short)
        short = ZH_SIGNAL_LABELS.get(short, short)
        short = translate_terms(short)
        short = re.split(r"[，。；]", short)[0].strip()
        short = re.sub(r"\d+\s*家.*$", "", short).strip()
        # 丢掉仍是英文蛇形键或过短噪声
        if re.fullmatch(r"[a-zA-Z0-9_]+", short or ""):
            short = ZH_SIGNAL_LABELS.get(short, "")
            short = translate_terms(short)
        if not short or len(short) < 2:
            return ""
        if short.startswith("整体") and "命中" not in short:
            return ""
        return short

    for ch in chapters:
        if ch.get("function") not in ("signal", "fraud", "tax", "authenticity"):
            continue
        for line in chapter_conclusion_lines(ch)[:3]:
            short = _clean(line)
            if not short or short in seen:
                continue
            seen.add(short)
            labels.append(short)
            if len(labels) >= limit:
                return labels
        meta = ch.get("meta") or {}
        for key in ("top_signals", "signal_counts"):
            raw = meta.get(key)
            if isinstance(raw, dict):
                for name, _cnt in sorted(raw.items(), key=lambda kv: -int(kv[1] or 0)):
                    lab = _clean(str(name))
                    if lab and lab not in seen:
                        seen.add(lab)
                        labels.append(lab)
                        if len(labels) >= limit:
                            return labels
    return labels


def build_bluf(
    *,
    scenario_key: str,
    chapters: list[dict[str, Any]],
    attribution: dict[str, Any],
    high_risk_ids: set[str] | None = None,
    strengths: list[str] | None = None,
    risks: list[str] | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    """分场景合成 BLUF（摘要第一句）+ 置信度 + Top 动作。

    禁止：conclusion + 「为什么：」+ risks[0] 的同质粘贴。
    """
    memo = resolve_memo_scenario(scenario_key, chapters, purpose=purpose)
    gq = governing_question(scenario_key, chapters, purpose=purpose)
    sample_n = int(attribution.get("sample_count") or 0)
    avg = attribution.get("avg_score")
    risk_level = (
        _score_to_risk_level(float(avg)) if isinstance(avg, (int, float)) else "—"
    )
    buckets = risk_buckets(attribution.get("risk_distribution"))
    blockers = _primary_blockers(attribution, risks)
    blocker_txt = "、".join(blockers) if blockers else "多项经营信号"
    cluster = _top_cluster(
        attribution.get("industry_distribution"),
        attribution.get("province_distribution"),
    )
    n_focus = len(high_risk_ids or set()) or int(
        sum(
            int((ch.get("meta") or {}).get("flagged_count") or 0)
            for ch in chapters
            if ch.get("function") in ("signal", "fraud")
        )
        or 0
    )
    conf = confidence_tag(sample_n)

    if memo == "loan":
        n = buckets["total"] or sample_n
        bluf = (
            f"{n} 家中 {buckets['approve']} 家可批、"
            f"{buckets['conditional']} 家需附加条件、"
            f"{buckets['reject']} 家不建议"
        )
        if blockers:
            bluf += f"，主要卡在〔{blocker_txt}〕"
        bluf += "。"
        actions = [
            f"对「不建议」档 {buckets['reject']} 家暂停新增敞口，先核进货销货与开票连续性。",
            f"对「附加条件」档明确担保/额度上限，并把〔{blocker_txt}〕写入贷后关注项。",
            "可批档按行业均值设额度天花板，放款前再核一次申报与开票是否同向。",
        ]
    elif memo == "rating":
        total = buckets["total"] or sample_n or 1
        creditworthy = buckets["approve"] + buckets["conditional"]
        # 可授信：低+中低+中等 中偏稳侧；用 approve+conditional 占比
        pct = round(creditworthy / total * 100) if total else 0
        bluf = f"群体信用「{risk_level}」，可授信占比约 {pct}%"
        if cluster:
            bluf += f"，尾部集中在〔{cluster}〕"
        elif blockers:
            bluf += f"，主要拖累〔{blocker_txt}〕"
        bluf += "。"
        actions = [
            f"优先对可授信档（约 {creditworthy} 家）做额度与等级复核。",
            f"尾部〔{cluster or blocker_txt}〕单独建关注名单，核对冲红与申报差异。",
            "评级口径与官方扣分项对齐后再对外披露等级。",
        ]
    elif memo == "warn":
        sigs = _top_signal_labels(chapters) or blockers
        sig_txt = "、".join(sigs[:3]) if sigs else blocker_txt
        involved = n_focus or buckets["reject"] or sample_n
        bluf = f"Top 异常信号〔{sig_txt}〕，涉及约 {involved} 家"
        if cluster:
            bluf += f"，集中〔{cluster}〕"
        bluf += "。"
        actions = [
            f"先拉出命中〔{sig_txt}〕的主体队列，核近 3 个月开票与申报是否同向。",
            "多重信号叠加的主体升为当日关注，避免只看单一指标。",
            "阈值已超的指标写入监测看板，按周复盘命中家数变化。",
        ]
    elif memo == "audit":
        involved = n_focus or buckets["reject"] or 0
        bluf = f"优先查约 {involved} 家，主要疑点〔{blocker_txt}〕，建议先调〔票据/申报凭证〕。"
        actions = [
            f"按〔{blocker_txt}〕排序抽查，先调红冲发票与对应销售方名单。",
            "交叉核申报收入与开票收入，不一致的进入第二核查队列。",
            "税务欠税/滞纳信号与发票疑点叠加的主体优先立案核查。",
        ]
    elif memo == "enterprise":
        bluf = f"综合评级「{risk_level}」"
        if blockers:
            bluf += f"，先盯〔{blocker_txt}〕"
        bluf += "。"
        actions = actionable_advice(risks, scenario="enterprise") or [
            "先处理最高风险信号，再回头看综合经营表现是否回升。"
        ]
    else:
        # custom：用章节论断拼一句决策向摘要，避免退回「中高风险+三类拖累」
        heads = []
        for ch in chapters[:3]:
            lines = chapter_conclusion_lines(ch)
            if lines:
                heads.append(translate_terms(strip_bullet_prefix(lines[0]).rstrip("。")))
        if heads:
            bluf = f"针对「{gq.rstrip('？?')}」：{'；'.join(heads[:2])}。"
        else:
            bluf = f"样本 {sample_n} 家，群体「{risk_level}」"
            if blockers:
                bluf += f"，关键卡点〔{blocker_txt}〕"
            bluf += "。"
        actions = actionable_advice(risks, scenario=memo) or [
            f"按〔{blocker_txt}〕核原始凭证与申报开票是否同向，形成可复核记录。"
        ]

    bluf = translate_terms(bluf)
    actions = _filter_actions([translate_terms(a) for a in actions[:3]])
    evidence = _summary_evidence(risks=risks, blockers=blockers, strengths=strengths)

    return {
        "memo_scenario": memo,
        "governing_question": gq,
        "bluf": bluf,
        "confidence": conf,
        "top_actions": actions,
        "blockers": blockers,
        "evidence": evidence,
        "risk_buckets": buckets,
        "strengths": [translate_terms(s) for s in (strengths or [])[:3]],
        "risks": [translate_terms(r) for r in (risks or [])[:4]],
    }


def _filter_actions(actions: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for a in actions or []:
        s = strip_bullet_prefix(str(a or "")).strip()
        if not s or _EMPTY_ACTION_RE.search(s):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out[:3]


def _summary_evidence(
    *,
    risks: list[str] | None,
    blockers: list[str] | None,
    strengths: list[str] | None,
) -> list[str]:
    """摘要「依据」：风险数字优先，卡点补缺；优势仅在改变处置时保留。"""
    out: list[str] = []
    seen: set[str] = set()
    for r in risks or []:
        item = translate_terms(strip_bullet_prefix(r)).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= 4:
            break
    if len(out) < 2:
        for b in blockers or []:
            item = translate_terms(str(b)).strip()
            if not item or item in seen:
                continue
            seen.add(item)
            out.append(item)
            if len(out) >= 4:
                break
    # 优势：最多 1 条，避免占版复读
    for s in (strengths or [])[:1]:
        item = translate_terms(strip_bullet_prefix(s)).strip()
        if item and item not in seen:
            out.append(f"相对稳健：{item}")
            break
    return out


def _soft_implication(memo: str) -> str:
    """无章节叙述时的短处置导向（不单独成「所以呢」标题）。"""
    defaults = {
        "loan": "授信需按分档收紧或附加条件。",
        "rating": "授信边界与尾部建档需单独安排。",
        "warn": "应优先盯高命中信号群体。",
        "audit": "应优先调票据与申报凭证核查。",
        "enterprise": "应优先补齐最高风险维度后再决定跟进。",
    }
    return defaults.get(memo, "据此安排下一步核查或授信动作。")


def _near_duplicate(a: str, b: str) -> bool:
    """粗判两句是否同义复读（去标点后包含关系）。"""
    def _norm(s: str) -> str:
        return re.sub(r"[\s，。；、：:（）()「」『』·\-—]", "", s or "")

    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 12 and shorter in longer


def compose_verdict_paragraph(ch: dict[str, Any], memo: str) -> str:
    """章节密段：判断 + 依据 + 处置（单段，禁止论断/所以呢分栏）。"""
    raw_lines = [
        translate_terms(strip_bullet_prefix(x)) for x in chapter_conclusion_lines(ch)[:3]
    ]
    lines: list[str] = []
    for ln in raw_lines:
        ln = re.sub(r"^结论[:：]\s*", "", ln).strip()
        ln = re.split(r"为什么[:：]", ln)[0].strip()
        if ln:
            lines.append(ln if ln.endswith(("。", "！", "？")) else ln + "。")

    judgment = lines[0] if lines else ""
    evidence = lines[1:2]
    narration = (ch.get("narration") or "").strip()
    if narration:
        first = re.split(r"[。！？]", translate_terms(narration))[0].strip()
        if first:
            n = first if first.endswith(("。", "！", "？")) else first + "。"
            if n and not any(_near_duplicate(n, x) for x in [judgment, *evidence]):
                evidence.append(n)

    actions = _filter_actions(_chapter_actions(ch, memo))
    parts: list[str] = []
    if judgment:
        parts.append(judgment)
    for e in evidence:
        if e and not any(_near_duplicate(e, p) for p in parts):
            parts.append(e)
    if actions:
        act = actions[0]
        act = act if act.endswith(("。", "！", "？")) else act + "。"
        if not any(_near_duplicate(act, p) for p in parts):
            parts.append(act)
    elif not parts:
        parts.append(_soft_implication(memo))
    elif len(parts) == 1:
        soft = _soft_implication(memo)
        if not _near_duplicate(soft, parts[0]):
            parts.append(soft)

    return "".join(parts)


def _chapter_actions(ch: dict[str, Any], memo: str) -> list[str]:
    existing = [strip_bullet_prefix(a) for a in (ch.get("actions") or []) if a]
    if existing:
        return _filter_actions(
            [translate_terms(a) for a in actionable_advice(existing, scenario=memo)[:5]]
        )
    lines = chapter_conclusion_lines(ch)
    advice = actionable_advice(lines, scenario=memo)
    return _filter_actions([translate_terms(a) for a in advice[:5]])


def make_action_title(ch: dict[str, Any], memo: str) -> str:
    """短论断标题（一行内），禁止整段结论粘贴与省略号腰斩。"""
    fn = ch.get("function") or ""
    lines = chapter_conclusion_lines(ch)
    first = ""
    if lines:
        first = translate_terms(strip_bullet_prefix(lines[0]))
        first = re.sub(r"^结论[:：]\s*", "", first)
        first = re.split(r"为什么[:：]", first)[0].strip()
        first = first.rstrip("。；;、")

    n_m = re.search(r"(\d+)\s*家", first)
    level_m = re.search(r"「([^」]*风险[^」]*)」", first)
    drag_m = re.search(r"拖累因素[:：]([^。]+)", first)
    drag0 = ""
    if drag_m:
        drag0 = drag_m.group(1).split("、")[0].strip()

    if level_m and ("风险判断" in first or "群体" in first or fn in ("score", "benchmark", "")):
        title = f"群体「{level_m.group(1)}」"
        if drag0 and len(drag0) <= 12:
            title += f"，{drag0}拖累"
        return title

    if fn == "fraud" and n_m:
        return f"{n_m.group(1)} 家发票舞弊需核查"
    if fn == "authenticity" and n_m:
        return f"{n_m.group(1)} 家多口径营收不一致"
    if fn == "tax" and n_m:
        return f"税务合规承压（{n_m.group(1)} 家相关）"
    if fn == "signal" and n_m:
        return f"{n_m.group(1)} 家预警信号待盯防"
    if fn == "trend":
        return "行业趋势分化，结构权重需复核"
    if fn == "financial":
        return "财务承压处需先核对报表口径"

    if first:
        clause = re.split(r"[，。；]", first)[0].strip()
        clause = re.sub(r"^全样本[（(][^）)]+[）)]", "全样本", clause)
        if 2 <= len(clause) <= 28:
            return clause
        if n_m:
            return f"{n_m.group(1)} 家需对照本模块数字处置"
        if level_m:
            return f"群体「{level_m.group(1)}」"

    fallback = {
        "fraud": "发票信号需作为附加核查条件",
        "authenticity": "申报与开票不一致需谨慎处置",
        "tax": "税务合规信号进入关注队列",
        "signal": "多重预警叠加，优先盯高命中群体",
        "score": "经营表现分化，结构决定授信边界",
        "benchmark": "同业对照提示额度与评级上限",
        "trend": "规模与趋势决定样本结构权重",
        "financial": "财务承压处需先核对报表口径",
    }.get(fn)
    if fallback:
        return fallback
    topic = (ch.get("topic_title") or ch.get("title") or "决策要点").strip()
    return f"{topic}需对照关键数字复核"[:28]


def enrich_decision_pages(
    chapters: list[dict[str, Any]],
    *,
    scenario_key: str,
    purpose: str | None = None,
) -> None:
    """原地装配：短论断标题 + 密段 + 增量处置（摘要已有则章节不复读空动作）。"""
    memo = resolve_memo_scenario(scenario_key, chapters, purpose=purpose)
    seen_titles: set[str] = set()
    fn_tag = {
        "score": "综合",
        "fraud": "发票",
        "authenticity": "真实性",
        "tax": "税务",
        "signal": "预警",
        "benchmark": "对标",
        "trend": "趋势",
        "financial": "财务",
    }
    for ch in chapters:
        if not ch.get("topic_title"):
            ch["topic_title"] = ch.get("title") or ""
        title = make_action_title(ch, memo)
        if title in seen_titles:
            tag = fn_tag.get(str(ch.get("function") or ""), "") or (ch.get("topic_title") or "")[:6]
            if tag and tag not in title:
                title = f"{title}（{tag}）"
        seen_titles.add(title)
        ch["action_title"] = title
        ch["title"] = title
        conclusions = chapter_conclusion_lines(ch)
        ch["decision_lines"] = [translate_terms(strip_bullet_prefix(x)) for x in conclusions[:3]]
        ch["verdict_paragraph"] = compose_verdict_paragraph(ch, memo)
        # 兼容旧字段：不再作为模板分栏，仅供测试/降级
        ch["so_what"] = ch["verdict_paragraph"]
        ch["actions"] = _filter_actions(_chapter_actions(ch, memo))


def apply_memo_to_slice_context(
    context: dict[str, Any],
    *,
    scenario_key: str,
    chapters: list[dict[str, Any]],
    attribution: dict[str, Any],
    high_risk_ids: set[str] | None = None,
    strengths: list[str] | None = None,
    risks: list[str] | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    """把决策备忘录字段写入 slice/custom 报告上下文（根装配出口）。"""
    enrich_decision_pages(chapters, scenario_key=scenario_key, purpose=purpose)
    memo = build_bluf(
        scenario_key=scenario_key,
        chapters=chapters,
        attribution=attribution,
        high_risk_ids=high_risk_ids,
        strengths=strengths,
        risks=risks,
        purpose=purpose,
    )
    context["governing_question"] = memo["governing_question"]
    context["memo_scenario"] = memo["memo_scenario"]
    context["summary_conclusion"] = memo["bluf"]
    context["executive_summary"] = memo["bluf"]
    context["confidence_tag"] = memo["confidence"]
    context["top_actions"] = memo["top_actions"]
    context["summary_blockers"] = memo["blockers"]
    context["summary_evidence"] = memo["evidence"]
    context["summary_strengths"] = memo["strengths"]
    context["summary_risks"] = memo["risks"]
    context["summary_highlights"] = {"strengths": [], "risks": []}
    if context.get("cover_meta") and isinstance(context["cover_meta"], dict):
        one = memo["bluf"]
        if "。" in one:
            one = one.split("。", 1)[0].strip() + "。"
        context["cover_meta"]["one_liner"] = one
        context["cover_meta"]["governing_question"] = memo["governing_question"]
    return memo


def build_enterprise_bluf(
    *,
    risk_level: str,
    hit_risk_count: int,
    checked_metric_count: int,
    weak_titles: list[str],
    risk_points: list[str],
    advice: list[str],
) -> dict[str, Any]:
    """个体报告 BLUF：值不值得做 + 先盯什么。"""
    gq = GOVERNING_QUESTIONS["enterprise"]
    blockers = [translate_terms(x) for x in (weak_titles or risk_points or [])[:2]]
    blocker_txt = "、".join(blockers) if blockers else "关键经营信号"
    bluf = (
        f"综合评级「{risk_level}」，命中风险指标 {hit_risk_count} 项"
        f"（已检 {checked_metric_count} 项）"
    )
    if blockers:
        bluf += f"，先盯〔{blocker_txt}〕"
    bluf += "。"
    actions = _filter_actions([translate_terms(a) for a in (advice or [])[:3]])
    if not actions:
        actions = [f"优先核查〔{blocker_txt}〕相关凭证与同业对照，再决定是否继续跟进。"]
    evidence = _summary_evidence(risks=risk_points, blockers=blockers, strengths=None)
    return {
        "memo_scenario": "enterprise",
        "governing_question": gq,
        "bluf": translate_terms(bluf),
        "top_actions": actions,
        "blockers": blockers,
        "evidence": evidence,
        "confidence": confidence_tag(1),
    }


def filter_empty_metrics(metrics: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """个体报告：丢掉无数值/无评级的空行，从根源去掉「暂无可用数据」刷屏。"""
    skip_rating = {"", "—", "【暂无可用数据】", "暂无可用数据", None}
    out: list[dict[str, Any]] = []
    for m in metrics or []:
        rating = str(m.get("rating") or "").strip()
        val = m.get("value")
        if rating in skip_rating and (val is None or str(val).strip() in ("", "—", "【暂无可用数据】")):
            continue
        if str(val).strip() in ("【暂无可用数据】", "暂无可用数据"):
            continue
        out.append(m)
    return out


def enrich_enterprise_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """个体分维：短论断标题 + 密段 + 空行折叠。"""
    enriched: list[dict[str, Any]] = []
    for sec in sections or []:
        metrics = filter_empty_metrics(sec.get("metrics"))
        if not metrics and not (sec.get("analysis") or {}).get("level_review"):
            continue
        title = sec.get("title") or "维度"
        risk = sec.get("risk_level") or ""
        if risk == "高":
            action_title = f"「{title}」承压，需优先核查"
        elif risk == "低":
            action_title = f"「{title}」相对稳健"
        else:
            action_title = f"「{title}」需对照标准复核"
        analysis = dict(sec.get("analysis") or {})
        level = translate_terms(analysis.get("level_review") or "").strip()
        risks_txt = translate_terms(analysis.get("risks") or "").strip()
        advice = translate_terms(analysis.get("advice") or "").strip()
        parts: list[str] = []
        for p in (level, risks_txt):
            if not p:
                continue
            p = p if p.endswith(("。", "！", "？")) else p + "。"
            if not any(_near_duplicate(p, x) for x in parts):
                parts.append(p)
        actions = _filter_actions(
            actionable_advice([advice] if advice else parts, scenario="enterprise")
        )
        if actions:
            act = actions[0]
            act = act if act.endswith(("。", "！", "？")) else act + "。"
            if not any(_near_duplicate(act, x) for x in parts):
                parts.append(act)
        if not parts:
            parts.append(_soft_implication("enterprise"))
        verdict = "".join(parts)
        enriched.append(
            {
                **sec,
                "topic_title": title,
                "title": action_title,
                "action_title": action_title,
                "metrics": metrics,
                "verdict_paragraph": verdict,
                "so_what": verdict,
                "actions": actions[:2],
            }
        )
    return enriched