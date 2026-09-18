"""Structured scope controls used by chat followup buttons."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics
from app.services import scope_state, session_store
from app.services.sync_runner import run_blocking


async def _demo_enterprise(db: AsyncSession) -> tuple[str, str] | None:
    row = (
        await db.execute(
            select(CoreMetrics.enterprise_id, CoreMetrics.display_name)
            .where(CoreMetrics.display_name.is_not(None))
            .order_by(CoreMetrics.enterprise_id)
            .limit(1)
        )
    ).first()
    if not row:
        return None
    return str(row[0]), str(row[1] or "演示企业")


async def handle_scope_change(
    *,
    db: AsyncSession,
    session_id: str,
    owner: str | None,
    followup: dict[str, Any],
) -> dict[str, Any]:
    params = followup.get("params") if isinstance(followup.get("params"), dict) else {}
    target = followup.get("target")
    state = await run_blocking(session_store.get_session, session_id) or {}
    current_state = state.get("dialogue_state") or scope_state.empty_dialogue_state()

    enterprise_id = str(params.get("enterprise_id") or "").strip() or None
    display_name = str(params.get("display_name") or "").strip() or None

    if params.get("use_demo") or (target == "individual" and not enterprise_id):
        demo = await _demo_enterprise(db)
        if demo is None:
            new_state = scope_state.switch_scope(current_state, target="unbound")
            facts = "当前数据集中没有可用于演示的企业主体，不能伪造演示企业。"
        else:
            enterprise_id, display_name = demo
            new_state = scope_state.switch_scope(
                current_state,
                target="individual",
                subject={"enterprise_id": enterprise_id, "display_name": display_name},
            )
            facts = f"演示范围已切换为企业主体「{display_name}」。这是真实脱敏数据，不是 mock 数据。"
    elif target == "individual" and enterprise_id:
        new_state = scope_state.switch_scope(
            current_state,
            target="individual",
            subject={
                "enterprise_id": enterprise_id,
                "display_name": display_name or enterprise_id,
            },
        )
        facts = f"分析范围已切换为企业主体「{display_name or enterprise_id}」。"
    elif target == "cohort":
        new_state = scope_state.switch_scope(current_state, target="cohort")
        facts = "分析范围已切换到全库群体视角。"
    else:
        new_state = scope_state.switch_scope(current_state, target="unbound")
        facts = "已清除个体主体，请重新选择分析范围。"

    from app.services import llm_reply

    reply, source = await llm_reply.generate_policy_reply(
        query=str(followup.get("label") or ""),
        route="scope_control",
        facts=facts,
        status="answered",
    )
    if not reply:
        reply = facts
        source = "template"

    public_state = scope_state.state_public(new_state)
    await run_blocking(
        session_store.store_session,
        session_id,
        "scope_control",
        query=str(followup.get("label") or ""),
        function="general",
        dimension="overall",
        enterprise_id=(
            public_state.get("subject", {}).get("enterprise_id")
            if public_state.get("scope") == "individual"
            else None
        ),
        owner=owner,
        reply=reply,
        dialogue_state=new_state,
    )
    return {
        "reply": reply,
        "reply_source": source,
        "analysis_mode": "rule",
        "parse_source": "scope_control",
        "intent": "scope_control",
        "function": "general",
        "dimension": "overall",
        "session_id": session_id,
        "dialogue_state": public_state,
        "ui": scope_state.ui_bundle(new_state),
        "data": {
            "claims": [],
            "primary": {
                "status": "answered",
                "route": "scope_control",
                "fallback": False,
                "semantic_frame": {
                    "policy_route": "scope_control",
                    "task_type": "policy",
                    "subject_scope": public_state.get("scope"),
                    "entities": [enterprise_id] if enterprise_id else [],
                },
            },
        },
    }
