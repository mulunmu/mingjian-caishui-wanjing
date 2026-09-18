"""Single persistence writer for successful semantic-primary turns."""
from __future__ import annotations

from typing import Any

from app.db.urls import get_sync_engine
from app.schemas.semantic_turn import SemanticTurnResult
from app.services import session_store
from app.services.sync_runner import run_blocking
from app.services.topic_memory import append_topic_blocking


class PrimaryPersistenceError(RuntimeError):
    """Raised when a primary turn cannot be durably recorded."""


_ROUTE_SUMMARIES = {
    "greeting": "用户问候",
    "capability": "系统能力询问",
    "product_faq": "产品功能说明",
    "feedback": "用户反馈",
    "out_of_domain": "域外问题弃权",
    "abuse": "不当表达降温",
    "language_switch": "语言切换",
    "unknown_entity": "企业未找到",
    "clarify": "请求补充信息",
    "refuse": "拒绝编造",
    "report": "报告请求",
}


def _plan_params(turn: SemanticTurnResult) -> dict[str, Any]:
    if turn.plan is None or not turn.plan.steps:
        return {}
    return dict(turn.plan.steps[0].params or {})


def _entities(turn: SemanticTurnResult) -> list[str]:
    entity = _plan_params(turn).get("entity")
    return [str(entity)] if entity else []


def _report_ids(turn: SemanticTurnResult) -> list[str]:
    report = turn.meta.get("report")
    candidates = [turn.meta.get("report_id")]
    if isinstance(report, dict):
        candidates.append(report.get("report_id"))
    result: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value not in result:
            result.append(value)
    return result


def _summary(turn: SemanticTurnResult, query: str) -> str:
    if turn.claims:
        return str(turn.claims[0].claim or "")[:160]
    return _ROUTE_SUMMARIES.get(turn.route.route, turn.reply or query or "")[:160]


def _function(turn: SemanticTurnResult) -> str:
    if turn.route.route in {"analysis", "report"}:
        return turn.route.domain or turn.route.route
    return "general"


def _dialogue_state(
    turn: SemanticTurnResult,
    entities: list[str],
    prior_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services import scope_state as ss

    state = ss.normalize_dialogue_state(prior_state)
    if entities:
        display_names = turn.meta.get("entity_display_names") or {}
        display_name = display_names.get(entities[0]) or entities[0]
        state = ss.switch_scope(
            state,
            target="individual",
            subject={"enterprise_id": entities[0], "display_name": display_name},
        )
    elif turn.route.route in {"analysis", "report"}:
        state = ss.switch_scope(state, target="cohort")
    focus = turn.meta.get("analysis_focus")
    if isinstance(focus, dict) and (focus.get("industry_l1") or focus.get("province")):
        state = ss.merge_analysis_focus(
            state,
            industry_l1=focus.get("industry_l1"),
            province=focus.get("province"),
        )
    inventory_focus = turn.meta.get('inventory_focus')
    if isinstance(inventory_focus, dict):
        state['inventory_focus'] = dict(inventory_focus)
    profile = turn.meta.get('profile_subject')
    if isinstance(profile, dict) and profile.get('enterprise_id'):
        state = ss.switch_scope(state, target='individual', subject={'enterprise_id': profile['enterprise_id'], 'display_name': profile.get('display_name') or profile['enterprise_id']})
    return state


async def persist_primary_turn(
    *,
    db,
    session_id: str,
    owner: str | None,
    query: str,
    turn: SemanticTurnResult,
    dialogue_state: dict[str, Any] | None = None,
) -> None:
    del db
    params = _plan_params(turn)
    entities = _entities(turn)
    filters = {
        key: value
        for key, value in params.items()
        if key not in {"query", "entity"} and value not in (None, "")
    }
    tool_plan = [step.model_dump() for step in (turn.plan.steps if turn.plan else [])]
    claim_ids = [
        str((claim.trace.query_id if claim.trace else "") or f"claim-{index}")
        for index, claim in enumerate(turn.claims, 1)
    ]
    report_ids = _report_ids(turn)

    stored = await run_blocking(
        session_store.store_session,
        session_id,
        turn.meta.get("session_intent") or turn.route.route,
        query=query,
        function=_function(turn),
        dimension=turn.route.domain or "overall",
        enterprise_id=entities[0] if entities else None,
        owner=owner,
        reply=turn.reply,
        followups=list(turn.followups),
        dialogue_state=_dialogue_state(turn, entities, dialogue_state),
        custom_report=turn.meta.get("custom_report_state"),
    )
    if not stored:
        raise PrimaryPersistenceError("session history persistence failed")

    try:
        await run_blocking(
            append_topic_blocking,
            get_sync_engine(),
            session_id=session_id,
            summary=_summary(turn, query),
            entities=entities,
            filters=filters,
            scenario=turn.route.domain,
            intent=turn.route.route,
            tool_plan=tool_plan,
            claim_ids=claim_ids,
            report_ids=report_ids,
        )
    except Exception as exc:
        raise PrimaryPersistenceError("topic persistence failed") from exc
