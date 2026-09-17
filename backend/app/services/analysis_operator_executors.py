"""Executable deterministic operators over upstream Claim bundles."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.schemas.claim import Claim, ClaimTrace, ClaimValue, claims_to_dict


def _input_claims(params: dict[str, Any]) -> list[Claim]:
    raw = params.get("claims") or []
    claims: list[Claim] = []
    for item in raw:
        try:
            claims.append(item if isinstance(item, Claim) else Claim.model_validate(item))
        except Exception:
            continue
    return claims


def _value(claim: Claim) -> float | None:
    if claim.value is None or claim.value.number is None:
        return None
    return float(claim.value.number)


def _label(claim: Claim) -> str:
    from app.services.metric_registry import zh_metric_label

    metric = str((claim.value.metric if claim.value else "") or "")
    return zh_metric_label(metric) or metric or "指标"


def _operator_claim(
    *,
    text: str,
    operator: str,
    field: str,
    number: float | None = None,
    unit: str = "",
) -> Claim:
    return Claim(
        claim=text,
        value=ClaimValue(metric=operator, number=number, unit=unit),
        trace=ClaimTrace(table="composition", field=field, query_id=f"Q_{operator}"),
        confidence="computed",
        evidence_chain=[f"operator={operator}", "source=upstream_claims"],
    )


def _summary(params: dict[str, Any]) -> dict[str, Any]:
    claims = _input_claims(params)
    if not claims:
        return {"claims": [], "followups": [], "meta": {"operator": "operator_summary"}}
    text = "；".join(claim.claim.strip() for claim in claims[:4] if claim.claim.strip())
    return {
        "claims": claims_to_dict(
            [_operator_claim(text=text, operator="operator_summary", field="claims")]
        ),
        "followups": [],
        "meta": {"operator": "operator_summary"},
    }


def _rank(params: dict[str, Any]) -> dict[str, Any]:
    claims = [claim for claim in _input_claims(params) if _value(claim) is not None]
    if not claims:
        return {"claims": [], "followups": [], "meta": {"operator": "operator_rank"}}
    ranked = sorted(claims, key=lambda item: _value(item) or 0.0, reverse=True)
    top = ranked[0]
    number = _value(top)
    unit = top.value.unit if top.value else ""
    return {
        "claims": claims_to_dict(
            [
                _operator_claim(
                    text=f"指标排名最高：{top.claim.strip()}",
                    operator="operator_rank",
                    field=str((top.value.metric if top.value else "") or ""),
                    number=number,
                    unit=unit,
                )
            ]
        ),
        "followups": [],
        "meta": {"operator": "operator_rank"},
    }


def _change_rate(params: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[Claim]] = {}
    for claim in _input_claims(params):
        number = _value(claim)
        metric = str((claim.value.metric if claim.value else "") or "")
        if number is not None and metric:
            grouped.setdefault(metric, []).append(claim)
    output: list[Claim] = []
    for metric, items in grouped.items():
        if len(items) < 2:
            continue
        base = _value(items[0])
        current = _value(items[-1])
        if base in (None, 0) or current is None:
            continue
        rate = round((current - base) / abs(base) * 100.0, 2)
        output.append(
            _operator_claim(
                text=f"{_label(items[-1])}变化率：{rate}%。",
                operator="operator_change_rate",
                field=metric,
                number=rate,
                unit="%",
            )
        )
    return {"claims": claims_to_dict(output), "followups": [], "meta": {"operator": "operator_change_rate"}}


def _proportion(params: dict[str, Any]) -> dict[str, Any]:
    claims = [claim for claim in _input_claims(params) if (_value(claim) or 0) >= 0]
    total = sum(_value(claim) or 0.0 for claim in claims)
    if not claims or total <= 0:
        return {"claims": [], "followups": [], "meta": {"operator": "operator_proportion"}}
    parts = [
        f"{_label(claim)}={round((_value(claim) or 0.0) / total * 100.0, 2)}%"
        for claim in claims
    ]
    return {
        "claims": claims_to_dict(
            [
                _operator_claim(
                    text="占比：" + "；".join(parts) + "。",
                    operator="operator_proportion",
                    field="claims",
                )
            ]
        ),
        "followups": [],
        "meta": {"operator": "operator_proportion"},
    }


def _group_compare(params: dict[str, Any], operator: str) -> dict[str, Any]:
    grouped: dict[str, dict[str, Claim]] = {}
    for claim in _input_claims(params):
        group = next(
            (
                str(item).split("=", 1)[1]
                for item in (claim.evidence_chain or [])
                if str(item).startswith("semantic_group_industry_l1=")
            ),
            "",
        )
        metric = str((claim.value.metric if claim.value else "") or "")
        if group and metric and _value(claim) is not None:
            grouped.setdefault(metric, {}).setdefault(group, claim)
    output: list[Claim] = []
    for metric, per_group in grouped.items():
        if len(per_group) < 2:
            continue
        parts = [f"{group}={_value(claim)}" for group, claim in per_group.items()]
        output.append(
            _operator_claim(
                text=f"{_label(next(iter(per_group.values())))}对比：" + "；".join(parts) + "。",
                operator=operator,
                field=metric,
            )
        )
    return {"claims": claims_to_dict(output), "followups": [], "meta": {"operator": operator}}


def _root_cause(params: dict[str, Any]) -> dict[str, Any]:
    claims = _input_claims(params)
    selected = [
        claim
        for claim in claims
        if (_value(claim) is not None and (_value(claim) or 0) < 0)
        or any(word in claim.claim for word in ("拖累", "偏低", "下降", "异常", "风险", "不一致"))
    ]
    if not selected:
        return {"claims": [], "followups": [], "meta": {"operator": "operator_root_cause"}}
    return {
        "claims": claims_to_dict(
            [
                _operator_claim(
                    text="主要风险驱动：" + "；".join(claim.claim.strip() for claim in selected[:5]),
                    operator="operator_root_cause",
                    field="claims",
                )
            ]
        ),
        "followups": [],
        "meta": {"operator": "operator_root_cause"},
    }


def _trend(params: dict[str, Any]) -> dict[str, Any]:
    claims = _input_claims(params)
    selected = [
        claim
        for claim in claims
        if any(word in claim.claim for word in ("同比", "环比", "趋势", "上升", "下降", "增长", "回落"))
        or any(
            token in str((claim.value.metric if claim.value else "") or "")
            for token in ("yoy", "trend", "change")
        )
    ]
    if not selected:
        return {"claims": [], "followups": [], "meta": {"operator": "operator_trend"}}
    return {
        "claims": claims_to_dict(
            [
                _operator_claim(
                    text="趋势结论：" + "；".join(claim.claim.strip() for claim in selected[:5]),
                    operator="operator_trend",
                    field="claims",
                )
            ]
        ),
        "followups": [],
        "meta": {"operator": "operator_trend"},
    }


def build_analysis_operator_executors(
    *,
    db,
    session_id: str,
) -> dict[str, Callable[..., Any]]:
    del db, session_id

    async def summary(*, params, dependency_results):
        del dependency_results
        return _summary(params)

    async def rank(*, params, dependency_results):
        del dependency_results
        return _rank(params)

    async def change_rate(*, params, dependency_results):
        del dependency_results
        return _change_rate(params)

    async def proportion(*, params, dependency_results):
        del dependency_results
        return _proportion(params)

    async def compare_industry(*, params, dependency_results):
        del dependency_results
        return _group_compare(params, "operator_compare_industry")

    async def compare_province(*, params, dependency_results):
        del dependency_results
        return _group_compare(params, "operator_compare_province")

    async def root_cause(*, params, dependency_results):
        del dependency_results
        return _root_cause(params)

    async def trend(*, params, dependency_results):
        del dependency_results
        return _trend(params)

    return {
        "operator_summary": summary,
        "operator_rank": rank,
        "operator_change_rate": change_rate,
        "operator_proportion": proportion,
        "operator_compare_industry": compare_industry,
        "operator_compare_province": compare_province,
        "operator_root_cause": root_cause,
        "operator_trend": trend,
    }
