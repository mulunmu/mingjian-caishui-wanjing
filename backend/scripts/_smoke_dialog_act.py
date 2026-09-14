"""DialogAct 负例冒烟：我可以分析哪些企业？→ 库存，不弃权/不甩 FAQ。"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import get_async_session_factory
from app.services import chat_router, dialog_act as da, llm_reply, scope_state as ss
from app.services.inventory_scope import inventory_answer


ABSTAIN_MARKERS = (
    "暂时无法判断好坏",
    "请先问系统能做什么",
)


async def main() -> None:
    # 强制走软降级，验证无 LLM 时也不弃权
    orig = llm_reply.llm_available
    llm_reply.llm_available = lambda: False  # type: ignore

    Session = get_async_session_factory()
    async with Session() as db:
        inv = await inventory_answer(db, ss.empty_dialogue_state(), ask_kind="overview")
        n = inv.get("sample_count") or 0
        assert n > 0, f"expected inventory sample_count>0, got {n}"
        assert str(n) in (inv.get("reply") or ""), inv.get("reply")

        out = await chat_router.route_chat(db, "我可以分析哪些企业？", session_id=None)
        reply = out.get("reply") or ""
        parse = out.get("parse_source") or ""
        print("--- NEGATIVE CASE ---")
        print("parse_source:", parse)
        print("reply:", reply[:400])
        assert parse == "negotiate_scope", parse
        assert str(n) in reply, reply
        assert "行业粗览" in reply or "可分析样本" in reply, reply
        for m in ABSTAIN_MARKERS:
            assert m not in reply, f"abstain leaked: {m}"

        # 行业切片不得复读整库范文
        slice_out = await chat_router.route_chat(
            db, "服务业的企业是那些", session_id=out.get("session_id")
        )
        sreply = slice_out.get("reply") or ""
        print("--- SLICE ---", sreply[:200])
        assert "服务" in sreply and "行业粗览" not in sreply, sreply
        assert "冒充" not in sreply

        # chip ≡ NL
        chip = await chat_router.route_chat(
            db,
            "我能分析哪些企业？",
            session_id=None,
            followup={
                "type": "dialog_act",
                "label": "我能分析哪些企业？",
                "params": {"act": "negotiate_scope", "confidence": 1.0},
            },
        )
        assert chip.get("parse_source") == "negotiate_scope"
        assert str(n) in (chip.get("reply") or "")

        # bind NL
        bind = await chat_router.route_chat(db, "随便来一家看看", session_id=None)
        assert bind.get("parse_source") in ("bind_subject", "switch_scope")
        ds = bind.get("dialogue_state") or {}
        assert ds.get("scope") == "individual", ds

        # gibberish → clarify
        clar = await chat_router.route_chat(db, "！！！哈哈哈xyz", session_id=None)
        assert clar.get("parse_source") == "clarify"
        assert "没太确定" in (clar.get("reply") or "")

        # cohort analyze after negotiate
        sid = out.get("session_id")
        cohort = await chat_router.route_chat(
            db,
            "全库哪里信号最多",
            session_id=sid,
            followup={
                "type": "dialog_act",
                "label": "全库哪里信号最多",
                "params": {
                    "act": "analyze",
                    "scenario": "warn",
                    "scope_target": "cohort",
                    "confidence": 1.0,
                },
            },
        )
        assert "暂时无法判断好坏" not in (cohort.get("reply") or "")
        print("cohort parse:", cohort.get("parse_source"), "intent:", cohort.get("intent"))

    llm_reply.llm_available = orig  # type: ignore
    print("ALL_DIALOG_ACT_AUDIT_OK")


if __name__ == "__main__":
    asyncio.run(main())
