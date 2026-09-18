"""Deterministic business responses for non-tool conversation routes."""
from __future__ import annotations

from app.schemas.conversation_route import ConversationPolicy, ConversationRoute
from app.schemas.semantic_turn import SemanticTurnResult


_POLICY_FACTS: dict[str, tuple[str, str]] = {
    "greeting": (
        "当前身份：明鉴财税风控助手。可协助企业财务、税务、发票、真实性、风险信号、评级和报告分析。",
        "answered",
    ),
    "capability": (
        "系统可分析企业财务、税务、发票、真实性、风险信号、评级与报告，也可解释系统功能和指标口径；"
        "真实数字、企业名单和风险结论只能来自系统数据。",
        "answered",
    ),
    "feedback": (
        "用户提交了反馈。系统会保留意见，但不要承诺具体功能变更或交付时间。",
        "answered",
    ),
    "out_of_domain": (
        "该问题超出当前财税风控数据范围。系统没有实时天气、公共闲聊或其他外部数据源，不能编造答案；"
        "可以说明边界并引导回企业经营、税务、发票、财务或报告。",
        "abstain",
    ),
    "abuse": (
        "用户表达不满或不当用语。不要升级冲突，不评判用户，继续按事实和边界提供帮助。",
        "answered",
    ),
    "language_switch": (
        "用户使用了非中文或要求切换语言。可以使用用户语言继续，并保持相同事实边界。",
        "answered",
    ),
    "unknown_entity": (
        "没有匹配到当前数据集中的企业。不得编造企业信息，应请用户提供系统内名称或脱敏编号。",
        "clarify",
    ),
    "clarify": (
        "缺少企业主体、分析范围或指标等必要槽位。一次只追问当前最关键的缺项。",
        "clarify",
    ),
    "refuse": (
        "用户请求可能要求编造数字、企业名单或风险结论。必须拒绝编造，并说明只能使用系统真实数据。",
        "abstain",
    ),
}


async def build_non_analysis_turn(
    route: ConversationRoute,
    query: str,
    *,
    policy: ConversationPolicy,
) -> SemanticTurnResult:
    if route.route in {"analysis", "report"}:
        raise ValueError(f"route requires tool execution: {route.route}")

    claims = []
    if route.route == "product_faq":
        from app.services.faq_kb import build_faq_claims

        claims, meta = build_faq_claims(query)
        facts = claims[0].claim if claims else "没有找到对应的产品说明。"
        status = "answered"
    else:
        try:
            facts, status = _POLICY_FACTS[route.route]
        except KeyError as exc:
            raise ValueError(f"unsupported non-analysis route: {route.route}") from exc
        meta = {}

    from app.services import llm_reply

    reply, source = await llm_reply.generate_policy_reply(
        query=query,
        route=route.route,
        facts=facts,
        status=status,
    )
    if not reply:
        reply = facts
        source = "template"
    elif not claims:
        from app.schemas.claim import Claim, ClaimTrace

        claims = [
            Claim(
                claim=facts,
                value=None,
                trace=ClaimTrace(
                    table="policy_facts",
                    field=route.route,
                    query_id=f"Q_policy_{route.route}",
                ),
                confidence="inferred",
            )
        ]

    return SemanticTurnResult(
        status=status,
        route=route,
        policy=policy,
        claims=claims,
        reply=reply,
        reply_source=source,
        meta=meta,
    )


def build_non_analysis_turn_sync(
    route: ConversationRoute,
    query: str,
    *,
    policy: ConversationPolicy,
) -> SemanticTurnResult:
    """Explicit deterministic fallback for callers that cannot await generation."""
    if route.route == "product_faq":
        from app.services.faq_kb import build_faq_claims

        claims, meta = build_faq_claims(query)
        return SemanticTurnResult(
            status="answered",
            route=route,
            policy=policy,
            claims=claims,
            reply=claims[0].claim,
            reply_source="template",
            meta=meta,
        )
    try:
        reply, status = _POLICY_FACTS[route.route]
    except KeyError as exc:
        raise ValueError(f"unsupported non-analysis route: {route.route}") from exc

    return SemanticTurnResult(
        status=status,
        route=route,
        policy=policy,
        reply=reply,
        reply_source="template",
    )
