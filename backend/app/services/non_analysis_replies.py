"""Deterministic business responses for non-tool conversation routes."""
from __future__ import annotations

from app.schemas.conversation_route import ConversationPolicy, ConversationRoute
from app.schemas.semantic_turn import SemanticTurnResult


_REPLIES: dict[str, tuple[str, str]] = {
    "greeting": (
        "你好。我是明鉴财税风控助手，可以继续分析企业风险，也可以直接问功能、口径或报告。",
        "answered",
    ),
    "capability": (
        "我可以分析企业财务、税务、发票、真实性、风险信号、评级与报告；也可以解释系统功能和指标口径。",
        "answered",
    ),
    "feedback": (
        "已收到你的反馈。系统会保留这条意见，但不会自动承诺功能变更。",
        "answered",
    ),
    "out_of_domain": (
        "这个问题超出了当前财税风控数据范围。我可以继续帮你看企业经营、税务、发票和风险预警。",
        "abstain",
    ),
    "abuse": (
        "我会继续按事实边界协助你。你可以直接说想查的企业、指标或报告类型。",
        "answered",
    ),
    "language_switch": (
        "I can continue in English or switch back to Chinese. "
        "Which enterprise or financial metric should I analyze?",
        "answered",
    ),
    "unknown_entity": ("没有找到对应企业，请提供企业名称或脱敏编号。", "clarify"),
    "clarify": ("请补充企业主体、指标名称或分析范围。", "clarify"),
    "refuse": ("数字、企业名单和风险结论只能来自系统真实数据，不能编造或伪造。", "abstain"),
}


def build_non_analysis_turn(
    route: ConversationRoute,
    query: str,
    *,
    policy: ConversationPolicy,
) -> SemanticTurnResult:
    if route.route in {"analysis", "report"}:
        raise ValueError(f"route requires tool execution: {route.route}")

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
        reply, status = _REPLIES[route.route]
    except KeyError as exc:
        raise ValueError(f"unsupported non-analysis route: {route.route}") from exc

    return SemanticTurnResult(
        status=status,
        route=route,
        policy=policy,
        reply=reply,
        reply_source="template",
    )
