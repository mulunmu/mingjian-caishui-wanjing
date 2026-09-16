"""Semantic-primary adapters for fixed and conversational reports.

The legacy router used to own report generation.  This module is the active
replacement: it keeps report structure and facts in the existing report
services, while the semantic layer only decides which report workflow to run.
"""
from __future__ import annotations

import logging
from typing import Any

from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.schemas.conversation_route import ConversationPolicyRegistry, ConversationRoute
from app.schemas.custom_report import CustomReportSpec
from app.schemas.semantic_turn import SemanticTurnResult

logger = logging.getLogger(__name__)


def _report_claim(*, text: str, metric: str, query_id: str) -> Claim:
    return Claim(
        claim=text,
        value=ClaimValue(metric=metric, number=None, unit=""),
        trace=ClaimTrace(table="reports", field="report", query_id=query_id),
        confidence="computed",
    )


def _subscriber_access(user: dict | None) -> bool:
    if not user:
        return False
    return (user.get("role") == "admin") or (user.get("plan") == "subscriber")


def _restricted_turn(
    *,
    route: ConversationRoute,
    reason: str | None = None,
) -> SemanticTurnResult:
    policy = ConversationPolicyRegistry.resolve(route)
    reply = reason or "报告功能为定制用户专享，请登录并升级后使用。"
    return SemanticTurnResult(
        status="answered",
        route=route,
        policy=policy,
        claims=[
            _report_claim(
                text=reply,
                metric="subscription_required",
                query_id="Q_report_subscription_gate",
            )
        ],
        reply=reply,
        followups=["查看报告生成方式", "返回对话"],
        reply_source="template",
        meta={"report_locked": True},
    )


async def _resolve_entities(db, raw_entities: list[str], enterprise_id: str | None) -> list[str]:
    if enterprise_id:
        return [enterprise_id]
    if not raw_entities:
        return []
    from app.services.assessment import resolve_enterprise_ids

    return await resolve_enterprise_ids(db, [str(item) for item in raw_entities if str(item).strip()])


def _report_meta(report_id: str, title: str, *, kind: str) -> dict[str, Any]:
    return {
        "report_id": report_id,
        "title": title,
        "kind": kind,
        "download_url": f"/api/v1/report/{report_id}/download",
    }


async def build_fixed_report_turn(
    *,
    db,
    session_id: str,
    owner: str | None,
    user: dict | None,
    query: str,
    route: ConversationRoute,
    enterprise_id: str | None = None,
    raw_entities: list[str] | None = None,
) -> SemanticTurnResult:
    """Generate an existing fixed report through the report service."""
    if not _subscriber_access(user):
        denied = "报告功能需要登录并使用定制账号。" if not user else "报告功能为定制用户专享，请升级后使用。"
        return _restricted_turn(route=route, reason=denied)

    entities = await _resolve_entities(db, raw_entities or [], enterprise_id)
    if raw_entities and not entities and not enterprise_id:
        return SemanticTurnResult(
            status="clarify",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply="未找到对应企业，请提供企业名称或脱敏编号后再生成报告。",
            reply_source="template",
        )

    try:
        if entities:
            from app.services.slice_report import generate_enterprise_report

            report_id, _path, context = await generate_enterprise_report(
                db,
                entities[0],
                owner=owner,
            )
            kind = "enterprise"
            title = str(context.get("title") or "企业风险报告")
            reply = f"已生成《{title}》，报告编号 {report_id}。可在报告中心查看或下载。"
        else:
            from app.services.scope_state import detect_scenario
            from app.services.slice_report import generate_slice_report

            scenario = detect_scenario(query) or "general"
            report_id, _path, context = await generate_slice_report(
                db,
                scenario=scenario,
                session_id=session_id,
                query=query,
                owner=owner,
            )
            kind = "slice"
            title = str(context.get("title") or "风险评估报告")
            reply = f"已生成《{title}》，报告编号 {report_id}。可在报告中心查看或下载。"
    except ValueError as exc:
        # Report services already produce user-safe data/scope errors.
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply=str(exc),
            followups=["换一个报告场景", "返回报告中心"],
            reply_source="template",
            meta={"report_error": str(exc)},
        )
    except Exception as exc:
        logger.warning("semantic report generation failed: %s", exc)
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply="报告生成暂不可用，请稍后重试。",
            followups=["稍后重试", "返回报告中心"],
            reply_source="template",
            meta={"report_error": "generation_failed"},
        )

    report = _report_meta(report_id, title, kind=kind)
    return SemanticTurnResult(
        status="answered",
        route=route,
        policy=ConversationPolicyRegistry.resolve(route),
        claims=[_report_claim(text=reply, metric="report", query_id="Q_report_generated")],
        reply=reply,
        followups=["查看并下载报告", "生成另一个报告"],
        reply_source="template",
        meta={
            "report": report,
            "report_id": report_id,
            "actions": [
                {"label": "查看并下载报告", "target": f"/report?highlight={report_id}"}
            ],
        },
    )


async def build_custom_report_turn(
    *,
    db,
    session_id: str,
    owner: str | None,
    user: dict | None,
    query: str,
    route: ConversationRoute,
    state: dict[str, Any] | None = None,
) -> SemanticTurnResult:
    """Advance the existing custom-report state machine and generate on confirm."""
    from app.services import custom_report as cr
    from app.services import assessment
    from app.services.slice_report import generate_custom_report

    if not _subscriber_access(user):
        return _restricted_turn(route=route)

    custom_state = dict(state or {})
    if not custom_state or not custom_state.get("active"):
        custom_state = cr.new_state()
    custom_state["active"] = True
    question = (query or "").strip()
    spec_obj: CustomReportSpec | None = None
    raw_spec = custom_state.get("spec")
    if raw_spec:
        try:
            spec_obj = CustomReportSpec.model_validate(raw_spec)
        except Exception:
            spec_obj = None

    if cr.is_exit(question):
        custom_state["active"] = False
        reply = "已退出定制。你可以继续选择固定报告，或随时重新说「我要定制报告」。"
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=ConversationPolicyRegistry.resolve(route),
            reply=reply,
            followups=["我要定制报告", "生成固定报告"],
            reply_source="template",
            meta={"custom_report_state": custom_state},
        )

    if (custom_state.get("stage") or "asking") == "propose" and cr.is_confirm(question):
        if spec_obj is None or not spec_obj.chapters:
            return SemanticTurnResult(
                status="clarify",
                route=route,
                policy=ConversationPolicyRegistry.resolve(route),
                reply="方案章节还不完整，请再告诉我你关注哪些风险（财务、税务、发票、真实性、评分、对标、趋势或信号）。",
                followups=list(cr.ASKING_FOLLOWUPS),
                reply_source="template",
                meta={"custom_report_state": custom_state},
            )
        try:
            enterprise_ids = await assessment.resolve_enterprise_ids(
                db, spec_obj.enterprises
            )
            report_id, _path, context = await generate_custom_report(
                db,
                spec=spec_obj,
                session_id=session_id,
                owner=owner,
                industry_l1=spec_obj.industry_l1,
                province=spec_obj.province,
                enterprise_ids=enterprise_ids,
            )
            title = str(context.get("title") or spec_obj.title or "定制风控报告")
            reply = f"已按你的方案生成《{title}》，报告编号 {report_id}。可在报告中心查看或下载。"
            custom_state["active"] = False
            report = _report_meta(report_id, title, kind="custom")
            return SemanticTurnResult(
                status="answered",
                route=route,
                policy=ConversationPolicyRegistry.resolve(route),
                claims=[_report_claim(text=reply, metric="report", query_id="Q_custom_report_generated")],
                reply=reply,
                followups=["查看并下载报告", "再定制一份", "换成固定报告"],
                reply_source="template",
                meta={
                    "report": report,
                    "report_id": report_id,
                    "custom_report_state": custom_state,
                    "actions": [
                        {"label": "查看并下载报告", "target": f"/report?highlight={report_id}"}
                    ],
                },
            )
        except ValueError as exc:
            custom_state["active"] = True
            return SemanticTurnResult(
                status="answered",
                route=route,
                policy=ConversationPolicyRegistry.resolve(route),
                reply=str(exc),
                followups=["调整范围", "换个章节组合", "退出定制"],
                reply_source="template",
                meta={"custom_report_state": custom_state, "report_error": str(exc)},
            )
        except Exception as exc:
            logger.warning("semantic custom report generation failed: %s", exc)
            custom_state["active"] = True
            return SemanticTurnResult(
                status="answered",
                route=route,
                policy=ConversationPolicyRegistry.resolve(route),
                reply="定制报告生成暂不可用，请稍后重试。",
                followups=["重新开始定制", "退出定制"],
                reply_source="template",
                meta={"custom_report_state": custom_state, "report_error": "generation_failed"},
            )

    result = await cr.next_turn(custom_state, question)
    reply = str(result.get("reply") or "").strip() or cr.rule_next_question(custom_state)
    followups = list(result.get("followups") or [])
    stage = str(result.get("stage") or "asking")
    custom_state["stage"] = stage
    if result.get("spec") is not None:
        custom_state["spec"] = result["spec"].model_dump()
    return SemanticTurnResult(
        status="answered" if stage == "propose" else "clarify",
        route=route,
        policy=ConversationPolicyRegistry.resolve(route),
        reply=reply,
        followups=followups,
        reply_source="llm" if result.get("llm") else "template",
        meta={
            "custom_report_state": custom_state,
            "custom_report_proposal": result.get("spec").model_dump()
            if result.get("spec") is not None
            else None,
            "cards": result.get("meta", {}).get("custom_proposal") if stage == "propose" else None,
        },
    )
