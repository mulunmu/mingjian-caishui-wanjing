"""范围协商：按 ask_kind / filters 查宽表。数字与名单只从引擎读。"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics
from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services import followup_items as fu
from app.services.intent_engine import industry_l1_options


def _claim(text: str, *, metric: str, number: float | int | None, unit: str, field: str) -> Claim:
    return Claim(
        claim=text,
        value=ClaimValue(metric=metric, number=number, unit=unit),
        trace=ClaimTrace(table="core_metrics", field=field, query_id="Q_inventory"),
        confidence="computed",
        evidence_chain=[f"metric={metric}", "source=core_metrics"],
    )


async def load_inventory(
    db: AsyncSession,
    *,
    industry_l1: str | None = None,
    province: str | None = None,
    top_n: int = 12,
) -> dict[str, Any]:
    """读库存；可按行业/地区过滤。"""
    filters = []
    if industry_l1:
        filters.append(CoreMetrics.industry_l1 == industry_l1)
    if province:
        filters.append(CoreMetrics.province == province)

    total_q = select(func.count()).select_from(CoreMetrics)
    if filters:
        total_q = total_q.where(*filters)
    total = int((await db.execute(total_q)).scalar() or 0)

    ind_rows = (
        await db.execute(
            select(CoreMetrics.industry_l1, func.count())
            .group_by(CoreMetrics.industry_l1)
            .order_by(func.count().desc())
        )
    ).all()
    industries = [
        {"industry_l1": ((ind or "其他").strip() or "其他"), "n": int(n or 0)}
        for ind, n in ind_rows
    ]

    name_q = select(
        CoreMetrics.enterprise_id,
        CoreMetrics.display_name,
        CoreMetrics.display_label,
        CoreMetrics.industry_l1,
    )
    if filters:
        name_q = name_q.where(*filters)
    name_rows = (await db.execute(name_q.order_by(CoreMetrics.enterprise_id).limit(top_n))).all()
    top_names: list[dict[str, Any]] = []
    for i, row in enumerate(name_rows, start=1):
        eid, dname, dlabel, ind = row
        top_names.append(
            {
                "enterprise_id": eid,
                "display_name": dname or dlabel or f"企业{i}",
                "industry_l1": ind or "其他",
            }
        )

    return {
        "sample_count": total,
        "industries": industries,
        "top_names": top_names,
        "industry_l1": industry_l1,
        "province": province,
    }


def _bind_items_from_names(names: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    items = []
    for n in names[:limit]:
        items.append(
            fu.item(
                type="switch_scope",
                label=f"看{n['display_name']}",
                target="individual",
                params={
                    "enterprise_id": n["enterprise_id"],
                    "display_name": n["display_name"],
                },
            )
        )
    return items


def _industry_slice_chips(industries: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    chips = []
    for x in industries:
        if int(x.get("n") or 0) <= 0:
            continue
        ind = x["industry_l1"]
        chips.append(
            fu.item(
                type="dialog_act",
                label=f"看{ind}有哪些（{x['n']}家）",
                params={
                    "act": "negotiate_scope",
                    "ask_kind": "list",
                    "industry_l1": ind,
                    "confidence": 1.0,
                },
            )
        )
        if len(chips) >= limit:
            break
    return chips


async def inventory_answer(
    db: AsyncSession,
    state: dict[str, Any] | None = None,
    *,
    ask_kind: str | None = None,
    industry_l1: str | None = None,
    province: str | None = None,
    top_n: int = 12,
) -> dict[str, Any]:
    """按槽位答这一问：overview / list / count / entry_help。不背说教稿。"""
    from app.services import scope_state as ss

    kind = (ask_kind or "overview").strip() or "overview"
    inv = await load_inventory(db, industry_l1=industry_l1, province=province, top_n=top_n)
    n = int(inv["sample_count"] or 0)
    names = inv["top_names"] or []
    inds = [x for x in inv["industries"] if int(x.get("n") or 0) > 0]
    scope_label = industry_l1 or province or ""

    if n <= 0 and kind in ("list", "count") and (industry_l1 or province):
        reply = (
            f"当前库里「{scope_label}」还没有样本。"
            "可以换个行业，或先看全库有哪些。"
        )
        items = [
            fu.item(
                type="dialog_act",
                label="看全库有哪些",
                params={"act": "negotiate_scope", "ask_kind": "overview", "confidence": 1.0},
            ),
            *ss.unbound_entry_items()[1:3],
        ]
        return {
            "reply": reply,
            "claims": [
                _claim(
                    f"{scope_label or '该范围'}样本 0 家。",
                    metric="sample_count",
                    number=0,
                    unit="家",
                    field="enterprise_id",
                )
            ],
            "followup_items": items,
            "meta": {"function": "inventory", "sample_count": 0, "ask_kind": kind, "inventory": True},
            "sample_count": 0,
            "inventory_focus": {"industry_l1": industry_l1, "province": province, "ask_kind": kind}
            if (industry_l1 or province)
            else None,
        }

    if kind == "count":
        label = scope_label or "全库"
        reply = f"「{label}」共有 {n} 家可分析样本。"
        if not scope_label:
            top = inds[:5]
            reply += "行业粗览：" + "、".join(f"{x['industry_l1']}{x['n']}家" for x in top) + "。"
        items = _industry_slice_chips(inds) if not scope_label else _bind_items_from_names(names)
        if scope_label:
            items.append(
                fu.item(
                    type="dialog_act",
                    label=f"列出{scope_label}企业",
                    params={
                        "act": "negotiate_scope",
                        "ask_kind": "list",
                        "industry_l1": industry_l1,
                        "province": province,
                        "confidence": 1.0,
                    },
                )
            )
        claims = [
            _claim(
                f"{label}样本 {n} 家。",
                metric="sample_count",
                number=n,
                unit="家",
                field="industry_l1" if industry_l1 else "enterprise_id",
            )
        ]
        return _pack(reply, claims, items, inv, kind, n, industry_l1, province)

    if kind == "list":
        label = scope_label or "全库"
        name_bits = "、".join(x["display_name"] for x in names) if names else "（暂无）"
        more = f"本轮列出前 {len(names)} 家" if n > len(names) else f"共 {n} 家"
        reply = f"「{label}」共 {n} 家。{more}：{name_bits}。可直接点名查看，或换个行业。"
        items = _bind_items_from_names(names)
        items.extend(
            [
                fu.item(
                    type="dialog_act",
                    label="换个行业看看",
                    params={"act": "negotiate_scope", "ask_kind": "overview", "confidence": 1.0},
                ),
                fu.item(
                    type="dialog_act",
                    label=f"看{label}群体风险" if scope_label else "看全库信号",
                    params={
                        "act": "analyze",
                        "scenario": "warn",
                        "scope_target": "cohort",
                        "industry_l1": industry_l1,
                        "confidence": 1.0,
                    },
                ),
            ]
        )
        claims = [
            _claim(
                f"{label}样本 {n} 家。",
                metric="sample_count",
                number=n,
                unit="家",
                field="industry_l1" if industry_l1 else "enterprise_id",
            )
        ]
        return _pack(reply, claims, items, inv, kind, n, industry_l1, province)

    if kind == "entry_help":
        reply = (
            "可以这样选范围：试用演示企业、从右侧列表点一家，或先看全库群体。"
            "也可以问某个行业有哪些企业。"
        )
        items = ss.unbound_entry_items()
        claims = [
            _claim(
                f"全库可分析样本 {n} 家。" if n else "暂无样本。",
                metric="sample_count",
                number=n,
                unit="家",
                field="enterprise_id",
            )
        ]
        return _pack(reply, claims, items, inv, kind, n, None, None)

    # overview
    if n <= 0:
        reply = "当前库里还没有可分析样本。请先接入数据。"
        items = [fu.item(type="navigate", label="打开数据接入", target="ingest")]
        claims = [
            _claim("可分析样本 0 家。", metric="sample_count", number=0, unit="家", field="enterprise_id")
        ]
        return _pack(reply, claims, items, inv, kind, 0, None, None)

    top_inds = inds[:5]
    ind_bits = "、".join(f"{x['industry_l1']}{x['n']}家" for x in top_inds)
    name_bits = "、".join(x["display_name"] for x in names[:5]) if names else ""
    reply = (
        f"当前可分析样本共 {n} 家。"
        f"行业粗览：{ind_bits}。"
    )
    if name_bits:
        reply += f"示例：{name_bits}。"
    reply += "想看某一行业名单，直接说行业名；或试用演示 / 列表选 / 看全库。"
    items = [
        *_industry_slice_chips(inds),
        *ss.unbound_entry_items()[1:4],
    ]
    claims = [
        _claim(
            f"可分析样本共 {n} 家。",
            metric="sample_count",
            number=n,
            unit="家",
            field="enterprise_id",
        ),
        _claim(
            f"有样本的行业大类约 {len(inds)} 个。",
            metric="industry_count",
            number=len(inds),
            unit="个",
            field="industry_l1",
        ),
    ]
    return _pack(reply, claims, items, inv, kind, n, None, None)


def _pack(reply, claims, items, inv, kind, n, industry_l1, province):
    focus = None
    if industry_l1 or province:
        focus = {"industry_l1": industry_l1, "province": province, "ask_kind": kind}
    return {
        "reply": reply,
        "claims": claims,
        "followup_items": items[:8],
        "meta": {
            "function": "inventory",
            "sample_count": n,
            "industries": inv.get("industries"),
            "top_names": inv.get("top_names"),
            "ask_kind": kind,
            "inventory": True,
        },
        "sample_count": n if not (industry_l1 or province) else None,
        "filtered_count": n if (industry_l1 or province) else None,
        "inventory_focus": focus,
    }


# ── subject 解析（bind）──

async def resolve_subject_ref(
    db: AsyncSession,
    subject_ref: str | None,
    *,
    current_eid: str | None = None,
) -> dict[str, Any] | None:
    ref = (subject_ref or "").strip()
    if not ref or re_demo(ref):
        return await _nth_subject(db, 0, exclude_eid=None)
    if re.search(r"换一家|换个|另一家", ref):
        return await _nth_subject(db, 0, exclude_eid=current_eid)

    m = re.search(r"企业\s*(\d+)", ref)
    if m:
        return await _nth_subject(db, max(int(m.group(1)) - 1, 0), exclude_eid=None)

    m = re.search(r"ENT\s*(\d+)", ref, re.I)
    if m:
        want = f"ENT{m.group(1)}"
        row = (
            await db.execute(
                select(
                    CoreMetrics.enterprise_id,
                    CoreMetrics.display_name,
                    CoreMetrics.display_label,
                )
                .where(
                    (CoreMetrics.display_name.ilike(f"%{want}%"))
                    | (CoreMetrics.enterprise_id.ilike(f"%{m.group(1)}%"))
                )
                .limit(1)
            )
        ).first()
        if row:
            return {"enterprise_id": row[0], "display_name": row[1] or row[2] or want}

    from app.services.intent_engine import _match_industry

    # 「建筑那家」→ 该行业第一家；纯行业词且带「那家/这家」才 bind
    if re.search(r"那家|这家|看看", ref):
        ind = _match_industry(ref)
        if ind:
            row = (
                await db.execute(
                    select(
                        CoreMetrics.enterprise_id,
                        CoreMetrics.display_name,
                        CoreMetrics.display_label,
                    )
                    .where(CoreMetrics.industry_l1 == ind)
                    .order_by(CoreMetrics.enterprise_id)
                    .limit(1)
                )
            ).first()
            if row:
                return {
                    "enterprise_id": row[0],
                    "display_name": row[1] or row[2] or f"{ind}样本",
                }

    row = (
        await db.execute(
            select(
                CoreMetrics.enterprise_id,
                CoreMetrics.display_name,
                CoreMetrics.display_label,
            )
            .where(
                (CoreMetrics.display_name.ilike(f"%{ref}%"))
                | (CoreMetrics.display_label.ilike(f"%{ref}%"))
            )
            .limit(1)
        )
    ).first()
    if row:
        return {"enterprise_id": row[0], "display_name": row[1] or row[2] or ref}
    return await _nth_subject(db, 0, exclude_eid=None)


def re_demo(ref: str) -> bool:
    return bool(re.search(r"演示|随便|任意|试用", ref))


async def _nth_subject(
    db: AsyncSession, index: int, *, exclude_eid: str | None
) -> dict[str, Any] | None:
    rows = (
        await db.execute(
            select(
                CoreMetrics.enterprise_id,
                CoreMetrics.display_name,
                CoreMetrics.display_label,
            )
            .order_by(CoreMetrics.enterprise_id)
            .limit(max(index + 3, 5))
        )
    ).all()
    if not rows:
        return None
    filtered = [r for r in rows if not exclude_eid or r[0] != exclude_eid]
    pick = filtered[min(index, len(filtered) - 1)] if filtered else rows[0]
    return {
        "enterprise_id": pick[0],
        "display_name": pick[1] or pick[2] or f"企业{index + 1}",
    }
