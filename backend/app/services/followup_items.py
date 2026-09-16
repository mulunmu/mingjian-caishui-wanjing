"""结构化追问（刀 1）：action / drilldown / navigate，禁止建议句复读进对话。

铁律：数字只来自引擎；本模块只路由 op，不编数。
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from app.services.chart_payloads import infer_chart

# 一期只开放这 3 个下钻 op
DRILLDOWN_OPS = frozenset({"group_by_industry", "top_list", "show_funnel"})


def item(
    *,
    type: str,
    label: str,
    claim_id: str | None = None,
    op: str | None = None,
    action: str | None = None,
    target: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"type": type, "label": label}
    if claim_id:
        out["claim_id"] = claim_id
    if op:
        out["op"] = op
    if action:
        out["action"] = action
    if target:
        out["target"] = target
    if params:
        out["params"] = params
    return out


def labels_of(items: list[dict[str, Any]]) -> list[str]:
    return [str(x.get("label") or "").strip() for x in items if (x.get("label") or "").strip()]


def _focus_params(meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """从本轮 meta / 焦点继承 industry_l1、province（供 dialog_act 槽位）。"""
    meta = meta or {}
    out: dict[str, Any] = {"scope_target": "cohort", "confidence": 1.0}
    for key in ("industry_l1", "province"):
        v = meta.get(key)
        if v:
            out[key] = v
    focus = meta.get("analysis_focus") if isinstance(meta.get("analysis_focus"), dict) else {}
    for key in ("industry_l1", "province"):
        if not out.get(key) and focus.get(key):
            out[key] = focus[key]
    return out


def normalize_legacy_strings(
    strings: list[str] | None,
    *,
    meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """旧版裸字符串 → 结构化芯片。

    契约：继续分析 → dialog_act(analyze)；生成报告 → navigate；调证 → action。
    禁止把「真实性/按地区趋势」落成 drilldown。
    """
    out: list[dict[str, Any]] = []
    focus = _focus_params(meta)
    for s in strings or []:
        t = (s or "").strip()
        if not t:
            continue
        t = t.replace("附录数据说明", "数据说明").replace("附录", "数据说明")
        # 多意图拼句：只取第一段，避免整串当一个 query
        if "；" in t or ";" in t:
            t = t.replace(";", "；").split("；", 1)[0].strip()
        if any(k in t for k in ("生成报告", "出报告", "报告中心", "出组合报告")):
            out.append(item(type="navigate", label=t if "报告" in t else "生成报告", target="report_generate"))
        elif any(k in t for k in ("风险预警", "风险态势", "查看预警")):
            out.append(item(type="navigate", label=t, target="overview"))
        elif any(k in t for k in ("数据接入", "数据怎么导入", "导入数据")):
            out.append(item(type="navigate", label=t, target="ingest"))
        elif t.startswith("调") or ("票据" in t and "凭证" in t):
            out.append(
                item(
                    type="action",
                    label=t,
                    action="manual_checklist",
                    params={
                        "hint": "这是人工核查动作：请按名单调取票据与货物凭证，系统不会替你外呼或调证。",
                    },
                )
            )
        elif any(k in t for k in ("真实性交叉", "经营真实性", "进一步看真实", "收入真实性")):
            out.append(
                item(
                    type="dialog_act",
                    label=t,
                    params={**focus, "act": "analyze", "scenario": "warn"},
                )
            )
        elif any(k in t for k in ("按地区", "地区拆分", "地区对比")):
            out.append(
                item(
                    type="dialog_act",
                    label=t,
                    params={**focus, "act": "analyze", "scenario": "rating"},
                )
            )
        elif any(k in t for k in ("各行业", "趋势走向", "行业趋势", "分析趋势", "对比各行业趋势")):
            # 「各行业」显式扩全库：清行业焦点
            params = {**focus, "act": "analyze", "scenario": "warn"}
            if "各行业" in t:
                params.pop("industry_l1", None)
            out.append(item(type="dialog_act", label=t, params=params))
        elif any(k in t for k in ("按行业拆", "行业拆开", "漏斗", "Top 名单", "Top名单", "异常主体 Top")):
            op = "show_funnel" if "漏斗" in t else (
                "top_list" if ("Top" in t or "名单" in t) else "group_by_industry"
            )
            out.append(item(type="drilldown", label=t, op=op, claim_id="c_fraud_flagged"))
        elif any(k in t for k in ("哪里可疑", "要查谁", "优先核查")):
            out.append(
                item(
                    type="dialog_act",
                    label=t,
                    params={**focus, "act": "analyze", "scenario": "audit"},
                )
            )
        else:
            # 默认：仍结构化为 analyze cohort，避免裸 query 再猜成假 drill
            out.append(
                item(
                    type="dialog_act",
                    label=t,
                    params={**focus, "act": "analyze"},
                )
            )
    return out[:6]


def build_fraud_followups(meta: dict[str, Any], *, claim_id: str = "c_fraud_flagged") -> list[dict[str, Any]]:
    """舞弊/可疑结论后的三类控件。"""
    n = int(meta.get("flagged_count") or 0)
    items: list[dict[str, Any]] = [
        item(
            type="drilldown",
            label=f"这{n}家按行业拆开看，哪些行业最集中？" if n else "按行业拆分看异常主体",
            claim_id=claim_id,
            op="group_by_industry",
        ),
        item(
            type="drilldown",
            label="列出异常主体 Top 名单（脱敏）",
            claim_id=claim_id,
            op="top_list",
            params={"limit": 15},
        ),
        item(
            type="drilldown",
            label="看风险筛查漏斗",
            claim_id=claim_id,
            op="show_funnel",
        ),
        item(
            type="action",
            label=f"调这{n}家的票据交易背景和货物凭证" if n else "调异常主体的票据与货物凭证",
            action="manual_checklist",
            params={
                "hint": (
                    f"人工核查清单：优先核对进销错配与冲红主体（约 {n} 家）。"
                    "请对照脱敏名单调取票据交易背景与货物凭证；系统无法代替外调。"
                ),
                "flagged_count": n,
            },
        ),
        item(type="navigate", label="生成报告", target="report_generate"),
        item(type="navigate", label="查看风险预警", target="overview"),
    ]
    return items[:6]


def build_faq_followups() -> list[dict[str, Any]]:
    """FAQ 结束后不再指回 FAQ 三件套，改为导航。"""
    return [
        item(type="navigate", label="打开数据接入", target="ingest"),
        item(type="navigate", label="打开报告生成", target="report_generate"),
        item(type="query", label="哪里可疑要查？"),
    ]


def build_default_followups(kind: str = "general") -> list[dict[str, Any]]:
    if kind == "faq":
        return build_faq_followups()
    return [
        item(type="query", label="哪里可疑要查？"),
        item(type="navigate", label="生成报告", target="report_generate"),
        item(type="navigate", label="查看风险预警", target="overview"),
    ]


def enrich_followups_for_meta(
    legacy: list[str] | None,
    meta: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """根据本轮 meta 优先产出结构化 followup；否则把旧字符串规范化。"""
    meta = meta or {}
    qt = meta.get("query_type") or ""
    fn = meta.get("function") or ""
    if qt == "faq" or fn == "faq":
        return build_faq_followups()
    if fn in ("fraud", "signal") or int(meta.get("flagged_count") or 0) > 0:
        # 有舞弊命中 → 舞弊专用三类控件
        if int(meta.get("flagged_count") or 0) > 0 or (meta.get("signal_counts") or meta.get("top_flags")):
            return build_fraud_followups(meta)
    # 把旧字符串映射成结构化（带本轮焦点；继续分析≠drill）
    focus_meta = {
        **meta,
        "industry_l1": meta.get("industry_l1"),
        "province": meta.get("province"),
        "analysis_focus": {
            "industry_l1": meta.get("industry_l1"),
            "province": meta.get("province"),
        },
    }
    items = normalize_legacy_strings(legacy, meta=focus_meta)
    if items:
        return items
    return build_default_followups()


async def run_drilldown(
    db: Any,
    *,
    op: str,
    claim_id: str | None,
    params: dict[str, Any] | None,
    session_context: dict[str, Any],
) -> dict[str, Any]:
    """沿上一结论下钻。成功返回 claims/meta/reply 骨架字段。"""
    from app.schemas.claim import Claim, ClaimTrace, ClaimValue
    from app.services.report_templates import zh_industry, zh_signal

    active = session_context.get("active_conclusion") or {}
    if claim_id and active.get("claim_id") and claim_id != active.get("claim_id"):
        # 允许同一会话内 fraud 主 claim
        if not str(claim_id).startswith("c_fraud"):
            return {
                "ok": False,
                "reply": "上一结论已过期或不匹配，请重新问「哪里可疑要查？」，再点下钻。",
                "claims": [],
                "followup_items": build_default_followups(),
                "meta": {"drilldown": "stale"},
            }

    if op not in DRILLDOWN_OPS:
        return {
            "ok": False,
            "reply": f"暂不支持该下钻操作（{op}）。当前可做：按行业拆分、名单 TopN、风险漏斗。",
            "claims": [],
            "followup_items": build_fraud_followups(active.get("meta") or {}),
            "meta": {"drilldown": "unsupported_op"},
        }

    meta = dict(active.get("meta") or {})
    firms: list[dict[str, Any]] = list(meta.get("flagged_firms") or meta.get("top_flags") or [])

    # 若会话里没有名单，现场重算舞弊切片（数字仍走引擎）
    if not firms and op in ("group_by_industry", "top_list", "show_funnel"):
        from app.services import judgment_service

        claims_f, meta_f = await judgment_service.build_fraud_claims(db, None)
        meta = {**meta, **(meta_f or {})}
        firms = list(meta.get("flagged_firms") or meta.get("top_flags") or [])
        _ = claims_f

    if op == "group_by_industry":
        if not firms:
            return {
                "ok": False,
                "reply": "没有可按行业拆分的异常主体名单。请先问「哪里可疑要查？」。",
                "claims": [],
                "followup_items": build_default_followups(),
                "meta": {"drilldown": "empty"},
            }
        cnt = Counter((f.get("industry_l1") or "其他") for f in firms)
        rows = sorted(cnt.items(), key=lambda kv: -kv[1])
        lines = [
            f"{zh_industry(ind) or ind} {n} 家" for ind, n in rows[:8]
        ]
        claim_text = (
            f"异常主体共 {len(firms)} 家，按行业集中在："
            + "、".join(lines)
            + "。样本量最大的行业应优先排查。"
        )
        claims = [
            Claim(
                claim=claim_text,
                value=ClaimValue(metric="flagged_by_industry", number=len(firms), unit="家"),
                trace=ClaimTrace(
                    table="enterprise_engine_features",
                    field="fraud_composite_score",
                    query_id="Q_fraud_by_industry",
                ),
                confidence="computed",
                evidence_chain=[f"{k}={v}" for k, v in rows[:6]],
            )
        ]
        chart = infer_chart({
            "shape": "categorical_distribution",
            "data": {
                "labels": [zh_industry(i) or i for i, _ in rows[:8]],
                "series": [{"name": "异常家数", "values": [n for _, n in rows[:8]]}],
            },
        })
        if chart:
            chart["title"] = "异常主体 · 行业分布"
        out_meta = {
            "function": "fraud",
            "query_type": "segmentation",
            "flagged_count": len(firms),
            "charts": chart,
            "flagged_firms": firms,
            "drilldown_op": op,
        }
        return {
            "ok": True,
            "reply": None,  # 交给 llm_reply / plain_language
            "claims": claims,
            "followup_items": build_fraud_followups(out_meta),
            "meta": out_meta,
        }

    if op == "top_list":
        limit = int((params or {}).get("limit") or 15)
        if not firms:
            return {
                "ok": False,
                "reply": "暂无异常主体名单可列。请先问「哪里可疑要查？」。",
                "claims": [],
                "followup_items": build_default_followups(),
                "meta": {"drilldown": "empty"},
            }
        top = firms[:limit]
        bullets = []
        for i, f in enumerate(top, 1):
            name = f.get("display_name") or f.get("display_label") or f"企业{(f.get('enterprise_id') or '')[:4]}"
            ind = zh_industry(f.get("industry_l1")) or f.get("industry_l1") or "—"
            sigs = "、".join(zh_signal(s) for s in (f.get("signals") or [])[:3]) or "综合异常"
            bullets.append(f"{i}. {name}（{ind}）· {sigs}")
        claim_text = f"异常主体脱敏名单（Top {len(top)} / 共 {len(firms)}）：\n" + "\n".join(bullets)
        claims = [
            Claim(
                claim=claim_text,
                value=ClaimValue(metric="flagged_top_list", number=len(top), unit="家"),
                trace=ClaimTrace(
                    table="enterprise_engine_features",
                    field="fraud_composite_score",
                    query_id="Q_fraud_top_list",
                ),
                confidence="computed",
                evidence_chain=[str(f.get("enterprise_id") or "")[:8] for f in top[:10]],
            )
        ]
        out_meta = {
            "function": "fraud",
            "flagged_count": len(firms),
            "flagged_firms": firms,
            "drilldown_op": op,
        }
        _table_chart = infer_chart({
            "shape": "tabular_rows",
            "data": {
                "columns": ["主体", "行业", "信号"],
                "rows": [
                    [
                        f.get("display_name") or f.get("display_label") or "—",
                        zh_industry(f.get("industry_l1")) or f.get("industry_l1") or "—",
                        "、".join(zh_signal(s) for s in (f.get("signals") or [])[:3]) or "—",
                    ]
                    for f in top
                ],
            },
        })
        if _table_chart:
            _table_chart["title"] = "异常主体 TopN"
        out_meta["charts"] = _table_chart
        return {
            "ok": True,
            "reply": None,
            "claims": claims,
            "followup_items": build_fraud_followups(out_meta),
            "meta": out_meta,
        }

    # show_funnel
    sc = meta.get("signal_counts") or {}
    sample_n = int(meta.get("sample_count") or 0)
    flagged_n = int(meta.get("flagged_count") or len(firms) or 0)
    if not sc and not flagged_n:
        return {
            "ok": False,
            "reply": "暂无漏斗数据。请先问「哪里可疑要查？」。",
            "claims": [],
            "followup_items": build_default_followups(),
            "meta": {"drilldown": "empty"},
        }
    labels = ["全样本"]
    values = [sample_n or sum(sc.values()) or flagged_n]
    if flagged_n:
        labels.append("异常主体")
        values.append(flagged_n)
    for k, v in list(sc.items())[:4]:
        labels.append(zh_signal(k))
        values.append(int(v))
    claim_text = (
        f"风险筛查漏斗：样本 {values[0]} 家 → 异常 {flagged_n} 家；"
        + "；".join(f"{zh_signal(k)} {v} 家" for k, v in list(sc.items())[:4])
    )
    claims = [
        Claim(
            claim=claim_text,
            value=ClaimValue(metric="flagged_count", number=flagged_n, unit="家"),
            trace=ClaimTrace(
                table="enterprise_engine_features",
                field="fraud_composite_score",
                query_id="Q_fraud_funnel",
            ),
            confidence="computed",
        )
    ]
    out_meta = {
        "function": "fraud",
        "flagged_count": flagged_n,
        "sample_count": sample_n,
        "signal_counts": sc,
        "flagged_firms": firms,
        "drilldown_op": op,
    }
    _funnel_chart = infer_chart({
        "shape": "hierarchical_stages",
        "data": {"labels": labels, "values": values},
    })
    if _funnel_chart:
        _funnel_chart["title"] = "风险筛查漏斗"
    out_meta["charts"] = _funnel_chart
    return {
        "ok": True,
        "reply": None,
        "claims": claims,
        "followup_items": build_fraud_followups(out_meta),
        "meta": out_meta,
    }
