"""AI 对话路由：功能×维度意图 → 风控分析 → 结论（隐藏证据）→ 追问"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.claim import Claim, ClaimTrace, ClaimValue, claims_to_dict
from app.schemas.semantic_query import SemanticQuery
from app.services import (
    conclusion_store,
    email_service,
    intent_engine,
    judgment_service,
    llm_reply,
    llm_semantic_parser,
    metric_registry,
    semantic_query,
    session_store,
    trusted_email_service,
    verification_service,
)
from app.services.intent_engine import IntentResult, industry_l1_options
from app.services.judgment_service import without_synthesis_claims
from app.services.report_templates import (
    CHAPTER_REGISTRY,
    CUSTOM_CHAPTERS,
    PremiumReportLocked,
    has_scenario_keyword,
    resolve_scenario,
    scenario_path_prompts,
)
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)


def _owner_email(user: dict | None) -> str | None:
    if not user:
        return None
    return ((user.get("sub") or user.get("email") or "").strip() or None)


def _scoped_scenario_prompts() -> list[str]:
    """范围化场景快捷：给出「{行业}的{场景}报告」组合，引导定制（非罗列空场景）。"""
    inds = industry_l1_options()[:2]
    if not inds:
        return scenario_path_prompts()
    return [
        f"生成{ind}的{title}"
        for ind in inds
        for title in ("财务健康体检报告", "税务合规体检报告", "发票舞弊排查报告")
    ]


def _user_has_subscriber_access(user: dict | None) -> bool:
    """与 require_plan('subscriber') 对齐：须登录且 admin 或 subscriber。"""
    if not user:
        return False
    role = user.get("role") or "user"
    plan = user.get("plan") or "free"
    return role == "admin" or plan == "subscriber"


def _subscription_denied_claim(user: dict | None) -> Claim | None:
    if _user_has_subscriber_access(user):
        return None
    detail = (
        "需要登录后使用定制功能。"
        if not user
        else "该功能为定制用户专享，请升级后使用。"
    )
    return Claim(
        claim=detail,
        value=ClaimValue(metric="subscription_required", number=None, unit=""),
        trace=ClaimTrace(table="auth", field="plan", query_id="Q_subscription_gate"),
        confidence="computed",
        evidence_chain=["require_plan=subscriber"],
    )


async def _route_enterprise(
    db: AsyncSession,
    query: str,
    enterprise_id: str,
    *,
    user: dict | None = None,
    scenario: str | None = None,
) -> dict:
    """个体下钻：按场景组织画像结论；「生成个体深度报告」时产出个体 PDF。"""
    from app.services import scope_state as ss

    out: dict = {
        "claims": [],
        "followups": [],
        "meta": {},
        "function": "enterprise",
        "dimension": "overall",
        "intent": "enterprise_overall",
        "report_meta": None,
        "industry_l1": None,
        "province": None,
    }
    intent_result = intent_engine.recognize(query)
    sc = scenario or ss.detect_scenario(query)
    if intent_result.function in ("report", "email_report"):
        denied = _subscription_denied_claim(user)
        if denied:
            out["claims"] = [denied]
            out["followups"] = ["升级定制后生成个体报告", "继续查看个体画像"]
            out["meta"] = {"enterprise_id": enterprise_id, "subscription_required": True}
            return out
        try:
            from app.services.slice_report import generate_enterprise_report

            report_id, _pdf_path, ctx = await generate_enterprise_report(
                db, enterprise_id, owner=_owner_email(user)
            )
            out["claims"] = [
                Claim(
                    claim=f"已生成《{ctx.get('title')}》，报告编号 {report_id}。",
                    value=ClaimValue(metric="report", number=None, unit=""),
                    trace=ClaimTrace(
                        table="conclusion_store",
                        field="claims",
                        query_id="Q_enterprise_report",
                    ),
                    confidence="computed",
                    evidence_chain=[
                        f"enterprise_id={enterprise_id[:8]}",
                        f"validation_ok={(ctx.get('validation') or {}).get('ok')}",
                    ],
                )
            ]
            out["followups"] = ["下载后核对数据说明", "继续追问同业基准", "回到个体画像"]
            out["report_meta"] = {
                "report_id": report_id,
                "download_url": f"/api/v1/report/{report_id}/download",
                "title": ctx.get("title"),
                "validation": ctx.get("validation"),
            }
            out["meta"] = {"enterprise_id": enterprise_id, "report_id": report_id, "scope": "individual"}
            return out
        except Exception as exc:
            logger.warning("enterprise report failed: %s", exc)
            out["claims"] = [
                Claim(
                    claim=f"个体深度报告生成失败：{exc}。请回到个体画像页重试。",
                    value=ClaimValue(metric="report_error", number=None, unit=""),
                    trace=ClaimTrace(
                        table="conclusion_store",
                        field="claims",
                        query_id="Q_enterprise_report_fail",
                    ),
                    confidence="inferred",
                )
            ]
            out["followups"] = list(judgment_service.ENTERPRISE_FOLLOWUPS)
            out["meta"] = {"enterprise_id": enterprise_id, "report_error": str(exc)}
            return out

    # R3：分场景组织（数字仍来自同一批引擎结果）
    claims, meta = await judgment_service.build_enterprise_scenario_claims(
        db, enterprise_id, scenario=sc
    )
    out["claims"] = claims
    out["meta"] = meta
    out["followups"] = judgment_service.derive_enterprise_followups(meta, claims)
    out["industry_l1"] = meta.get("industry_l1")
    out["province"] = meta.get("province")
    out["intent"] = f"enterprise_{sc or 'overall'}"
    return out


def _custom_report_response(
    sid: str,
    *,
    reply: str,
    reply_source: str,
    followups: list[str],
    meta: dict,
    report_meta: dict | None,
    custom_state: dict,
    industry_l1: str | None,
    province: str | None,
) -> dict:
    """把一轮定制对话封装成与 route_chat 一致的响应形状（前端零改动即可渲染）。"""
    data = {
        "function": "custom_report",
        "dimension": "overall",
        "query_type": None,
        "semantic_query": None,
        "industry_l1": industry_l1,
        "province": province,
        "enterprise_id": None,
        "claims": [],
        "followups": followups,
        "conclusion_id": None,
        "evidence_hidden": True,
        "coverage": [],
        "report_hint": None,
        "actions": meta.get("actions", []),
        "guidance_cards": meta.get("guidance_cards", []),
        "slice": {k: v for k, v in meta.items() if k not in ("actions", "charts")},
        "custom_stage": custom_state.get("stage"),
    }
    if report_meta:
        data["report"] = report_meta
    return {
        "reply": reply,
        "reply_source": reply_source,
        "analysis_mode": "rule",
        "parse_source": "llm" if reply_source == "llm" else "rule",
        "judgment_modes": {
            "analysis": "rule",
            "parse": "llm" if reply_source == "llm" else "rule",
            "narration": "llm" if reply_source == "llm" else "rule",
        },
        "intent": "custom_report_overall",
        "function": "custom_report",
        "dimension": "overall",
        "query_type": None,
        "enterprise_id": None,
        "enterprise_label": None,
        "data": data,
        "charts": None,
        "session_id": sid,
        "conclusion_id": None,
    }


def _chapter_name_to_fn(name: str) -> str | None:
    """章节标题/键 → 章节键（用于「换章节：标题」卡片反解）。"""
    for fn, entry in CHAPTER_REGISTRY.items():
        if entry["title"] == name or fn == name:
            return fn
    return None


def _apply_custom_adjustment(spec_obj, q: str):
    """确定性地应用拦截卡片的调整指令（不等用户口述重来）。

    返回 (new_spec, mode)：mode ∈ {'adjust' 改后重校验, 'reask' 回提问阶段, 'none' 非调整指令}。
    """
    from app.schemas.custom_report import CustomReportSpec

    data = spec_obj.model_dump()
    if q == "改用全部样本":
        data.update(industry_l1=None, province=None, enterprises=[])
        return CustomReportSpec(**data), "adjust"
    if q == "保留企业，去掉范围过滤":
        data.update(industry_l1=None, province=None)
        return CustomReportSpec(**data), "adjust"
    if q.startswith("换章节："):
        fn = _chapter_name_to_fn(q[len("换章节："):].strip())
        if fn:
            data["chapters"] = [fn]
            return CustomReportSpec(**data), "adjust"
        return spec_obj, "none"
    if q == "自定义修改范围":
        data.update(industry_l1=None, province=None, enterprises=[])
        return CustomReportSpec(**data), "reask"
    return spec_obj, "none"


async def _custom_adjustment_followups(db, spec, validation) -> list[dict]:
    """拦截时的可点击调整卡片：① 改用全部样本 ② 保留企业去范围 ③ 换章节 ④ 自定义。

    返回 {label, description} 卡片；label 即 followup 文本（点击触发 _apply_custom_adjustment）。
    """
    from app.services.slice_report import validate_custom_report

    chapters = list(spec.chapters or [])
    cards: list[dict] = []

    # ① 改用全部样本：请求章节在全样本下确有数据才给（避免二次空拦截）
    if spec.industry_l1 or spec.province:
        full = await validate_custom_report(db, chapters=chapters, industry_l1=None, province=None)
        if any(full["chapters"].get(fn, {}).get("available") for fn in chapters):
            cards.append({"label": "改用全部样本", "description": "取消行业、地区过滤，使用全部样本"})

    # ② 保留指定企业、去掉行业/地区过滤（有企业且当前有范围过滤时）
    if spec.enterprises and (spec.industry_l1 or spec.province):
        ent_names = "、".join(spec.enterprises)
        cards.append({"label": "保留企业，去掉范围过滤", "description": f"保留 {ent_names}，取消行业、地区筛选"})

    # ③ 换章节：当前范围（含指定企业）下其他有数据的章节
    alt_chapters = [f for f in CHAPTER_REGISTRY if f not in chapters]
    if alt_chapters:
        alts = await validate_custom_report(
            db, chapters=alt_chapters,
            industry_l1=spec.industry_l1, province=spec.province,
            enterprise_ids=validation.get("enterprise_ids") or None,
        )
        for fn in alt_chapters:
            if alts["chapters"].get(fn, {}).get("available"):
                title = CHAPTER_REGISTRY[fn]["title"]
                cards.append({"label": f"换章节：{title}", "description": f"改为当前范围下有数据的章节「{title}」"})

    # ④ 自定义修改范围
    cards.append({"label": "自定义修改范围", "description": "重新告诉我行业、地区或目标企业"})
    return cards


async def _custom_proposal_with_validation(db, spec) -> dict:
    """propose 阶段的数据驱动校验（元数据接口在组装好完整参数后立即调用）。

    返回 {reply, followups, empty, blocked, validation}：
    - 全部章节无数据 → blocked（不开放「确认生成」），给出根因 + 可点击调整卡片；
    - 部分章节无数据 → 保留「确认生成」，明确告知哪些章节将不出现；
    - 全部有数据 → 正常方案 +「确认生成」。
    """
    from app.services import assessment as _assessment
    from app.services import custom_report as cr
    from app.services.slice_report import custom_report_block_reason, validate_custom_report

    chapters = list(spec.chapters or [])
    enterprise_ids = await _assessment.resolve_enterprise_ids(db, spec.enterprises)
    validation = await validate_custom_report(
        db,
        chapters=chapters,
        industry_l1=spec.industry_l1,
        province=spec.province,
        enterprise_ids=enterprise_ids or None,
    )
    empty = [fn for fn in chapters if not validation["chapters"].get(fn, {}).get("available")]
    base = cr.proposal_text(spec)

    if empty and len(empty) == len(chapters):
        reason = await custom_report_block_reason(
            db,
            industry_l1=spec.industry_l1,
            province=spec.province,
            enterprise_ids=enterprise_ids or None,
            scope_sample_count=validation.get("scope_sample_count") or 0,
        )
        names = "、".join(CHAPTER_REGISTRY[fn]["title"] for fn in empty if fn in CHAPTER_REGISTRY)
        reply = (
            f"{base}\n\n"
            f"❗ 当前组合没有匹配的「{names}」数据，无法生成这份报告。\n"
            f"原因：{reason}\n\n"
            "你可以直接选择下面任一调整方案（点击右侧卡片）："
        )
        cards = await _custom_adjustment_followups(db, spec, validation)
        followups = [c["label"] for c in cards]
        return {"reply": reply, "followups": followups, "cards": cards, "empty": empty, "blocked": True, "validation": validation}
    else:
        reply = base
        if empty:
            names = "、".join(CHAPTER_REGISTRY[fn]["title"] for fn in empty if fn in CHAPTER_REGISTRY)
            reply += (
                f"\n\n⚠️ 提示：「{names}」在当前范围暂无可用数据，生成后该章节将不出现。"
                "可改用「全部样本」或换章节，或直接确认生成（其余章节照常输出）。"
            )
        followups = list(cr.PROPOSE_FOLLOWUPS)
        return {"reply": reply, "followups": followups, "cards": [], "empty": empty, "blocked": False, "validation": validation}


async def _route_custom_report(
    db: AsyncSession,
    query: str,
    sid: str,
    *,
    user: dict | None,
    session_context: dict,
) -> dict:
    """AI 主导的定制报告对话（asking → propose → 确认生成）。

    状态机推进见 app.services.custom_report；此处只做路由 + 响应封装 + 会话态持久化。
    AI 只决定「章节子集 + 范围 + 标题 + 语气」，不产生任何数字（铁律）。
    """
    from app.schemas.custom_report import CustomReportSpec
    from app.services import custom_report as cr

    state = dict(session_context.get("custom_report") or {})
    if not state:
        state = cr.new_state()
    state["active"] = True

    reply = ""
    followups: list[str] = []
    meta: dict = {}
    report_meta: dict | None = None
    industry_l1: str | None = None
    province: str | None = None
    reply_source = "rule"
    guidance_cards: list[dict] = []

    q = (query or "").strip()

    if cr.is_exit(q):
        state["active"] = False
        reply = "已退出定制。你可以继续选固定报告，或随时再说「我要定制报告」。"
        followups = ["我要定制报告", *scenario_path_prompts()[:3]]
        meta["actions"] = [
            {"label": "直接生成固定报告（6 套模板）", "target": "/?wizard=1"},
            {"label": "重新开始 AI 定制", "target": "/research?custom=1"},
        ]
    elif (state.get("stage") or "asking") == "propose":
        spec = state.get("spec")
        spec_obj = CustomReportSpec.model_validate(spec) if spec else None
        handled = False

        # 1) 拦截卡片的确定性调整指令（点击卡片即生效，不等用户口述重来）
        if spec_obj is not None:
            spec_obj, adjust_mode = _apply_custom_adjustment(spec_obj, q)
            if adjust_mode == "reask":
                handled = True
                state["spec"] = spec_obj.model_dump()
                state["stage"] = "asking"
                reply = "好的，请告诉我新的范围：行业（如制造、批发零售）、地区（如广东、浙江），或直接说「全部样本」。"
                followups = ["全部样本", "退出定制"]
            elif adjust_mode == "adjust":
                handled = True
                proposal = await _custom_proposal_with_validation(db, spec_obj)
                state["spec"] = spec_obj.model_dump()
                state["stage"] = "propose"
                state["validation"] = proposal["validation"]
                state["empty_chapters"] = proposal["empty"]
                reply = proposal["reply"]
                followups = list(proposal["followups"])
                guidance_cards = list(proposal.get("cards", []))

        # 2) 确认生成：生成前再跑一次校验兜底（即便前端漏放确认按钮，也绝不生成空报告）
        if not handled and cr.is_confirm(q):
            if spec_obj is None or not spec_obj.chapters:
                state["stage"] = "asking"
                reply = "方案章节还不完整，请再告诉我你关注哪些风险（财务/税务/发票舞弊/真实性/评分/对标/趋势/信号）。"
                followups = list(cr.ASKING_FOLLOWUPS)
            else:
                proposal = await _custom_proposal_with_validation(db, spec_obj)
                if proposal["blocked"]:
                    state["empty_chapters"] = proposal["empty"]
                    reply = proposal["reply"]
                    followups = list(proposal["followups"])
                    guidance_cards = list(proposal.get("cards", []))
                else:
                    try:
                        from app.services import assessment
                        from app.services.slice_report import generate_custom_report

                        enterprise_ids = await assessment.resolve_enterprise_ids(db, spec_obj.enterprises)
                        report_id, _pdf, ctx = await generate_custom_report(
                            db,
                            spec=spec_obj,
                            session_id=sid,
                            owner=_owner_email(user),
                            industry_l1=spec_obj.industry_l1,
                            province=spec_obj.province,
                            enterprise_ids=enterprise_ids or None,
                        )
                        industry_l1 = spec_obj.industry_l1
                        province = spec_obj.province
                        report_meta = {
                            "report_id": report_id,
                            "download_url": f"/api/v1/report/{report_id}/download",
                            "title": ctx.get("title"),
                            "validation": ctx.get("validation"),
                        }
                        # 以实际生成为准：比对请求章节与生成章节，告知真正被跳过的章节
                        generated_fns = {ch.get("function") for ch in (ctx.get("chapters") or [])}
                        skipped = [fn for fn in spec_obj.chapters if fn not in generated_fns]
                        if skipped:
                            names = "、".join(CHAPTER_REGISTRY[fn]["title"] for fn in skipped if fn in CHAPTER_REGISTRY)
                            reply = (
                                f"已生成《{ctx.get('title')}》（编号 {report_id}）。"
                                f"注意：「{names}」在当前范围暂无数据已跳过，建议改用「全部样本」范围查看。"
                            )
                        else:
                            reply = f"已按你的方案生成《{ctx.get('title')}》，报告编号 {report_id}。可在报告中心查看、下载。"
                        followups = ["再定制一份", "换成固定报告"]
                        meta["actions"] = [
                            {"label": "查看并下载报告", "target": f"/report?highlight={report_id}"},
                            {"label": "再定制一份", "target": "/research?custom=1"},
                        ]
                        meta["report_id"] = report_id
                        state["active"] = False
                    except Exception as exc:
                        logger.warning("custom report generation failed: %s", exc)
                        reply = (
                            f"定制报告生成失败：{exc}。"
                            "若刚才对话已定好方案，可再说一次「确认生成」重试；"
                            "或调整行业/章节后重试，也可改用报告中心快捷模板。"
                        )
                        followups = ["重新开始定制", "打开报告生成向导"]
                        meta["actions"] = [{"label": "打开报告生成向导", "target": "/?wizard=1"}]
                        meta["report_error"] = str(exc)

        # 3) propose 阶段非确认非调整 → 继续推进（允许用户口述改方案）
        elif not handled:
            result = await cr.next_turn(state, q)
            reply = result["reply"]
            followups = list(result["followups"])
            reply_source = "llm" if result.get("llm") else "rule"
            state["stage"] = result.get("stage") or state.get("stage") or "asking"
            if result.get("spec") is not None:
                state["spec"] = result["spec"].model_dump()
            if result.get("spec") is not None and result.get("stage") == "propose":
                proposal = await _custom_proposal_with_validation(db, result["spec"])
                state["validation"] = proposal["validation"]
                state["empty_chapters"] = proposal["empty"]
                reply = proposal["reply"]
                followups = list(proposal["followups"])
                guidance_cards = list(proposal.get("cards", []))
            meta = dict(result.get("meta") or {})

    else:
        # asking 阶段：必须推进 next_turn（此前误把 next_turn 挂在 propose 分支内 → 空气泡）
        result = await cr.next_turn(state, q)
        reply = result["reply"]
        followups = list(result["followups"])
        reply_source = "llm" if result.get("llm") else "rule"
        state["stage"] = result.get("stage") or state.get("stage") or "asking"
        if result.get("spec") is not None:
            state["spec"] = result["spec"].model_dump()
        if result.get("spec") is not None and result.get("stage") == "propose":
            proposal = await _custom_proposal_with_validation(db, result["spec"])
            state["validation"] = proposal["validation"]
            state["empty_chapters"] = proposal["empty"]
            reply = proposal["reply"]
            followups = list(proposal["followups"])
            guidance_cards = list(proposal.get("cards", []))
        meta = dict(result.get("meta") or {})

    # 兜底：绝不返回空正文（前端会只剩规则引擎徽章）
    if not (reply or "").strip():
        reply = cr.rule_next_question(state)
        if not followups:
            followups = list(cr.ASKING_FOLLOWUPS)

    await run_blocking(
        session_store.store_session,
        sid,
        intent="custom_report_overall",
        function="custom_report",
        dimension="overall",
        industry_l1=industry_l1,
        province=province,
        query=query,
        custom_report=state,
        owner=_owner_email(user),
        reply=reply,
        followups=list(followups or []),
    )

    if guidance_cards:
        meta["guidance_cards"] = guidance_cards

    return _custom_report_response(
        sid,
        reply=reply,
        reply_source=reply_source,
        followups=followups,
        meta=meta,
        report_meta=report_meta,
        custom_state=state,
        industry_l1=industry_l1,
        province=province,
    )


_VERIFY_CODE_RE = re.compile(r"^\d{6}$")


def _email_flow_response(
    sid: str,
    *,
    reply: str,
    followups: list[str],
    meta: dict | None = None,
    report_meta: dict | None = None,
) -> dict:
    """对话内邮件验证/发送分支的响应（与 route_chat 同构，前端零改动渲染）。"""
    meta = meta or {}
    data = {
        "function": "email_report",
        "dimension": "overall",
        "query_type": None,
        "semantic_query": None,
        "industry_l1": None,
        "province": None,
        "enterprise_id": None,
        "claims": [],
        "followups": followups,
        "conclusion_id": None,
        "evidence_hidden": True,
        "coverage": [],
        "report_hint": None,
        "actions": meta.get("actions", []),
        "slice": {k: v for k, v in meta.items() if k != "actions"},
    }
    if report_meta:
        data["report"] = report_meta
    return {
        "reply": reply,
        "reply_source": "rule",
        "analysis_mode": "rule",
        "parse_source": "rule",
        "judgment_modes": {"analysis": "rule", "parse": "rule", "narration": "rule"},
        "intent": "email_report",
        "function": "email_report",
        "dimension": "overall",
        "query_type": None,
        "enterprise_id": None,
        "enterprise_label": None,
        "data": data,
        "charts": None,
        "session_id": sid,
        "conclusion_id": None,
    }


async def _route_email_verify_code(
    db: AsyncSession,
    sid: str,
    query: str,
    pending: dict,
    *,
    user: dict | None,
    session_context: dict,
) -> dict:
    """对话内验证码回复：消费验证码 → 发送报告 → 验证通过即受信。"""
    recipient = (pending.get("recipient") or "").strip().lower()
    owner = (pending.get("user_email") or "").strip().lower()
    report_id = pending.get("report_id")
    title = pending.get("title") or "风控报告"
    pdf_path = pending.get("pdf_path")
    report_meta = pending.get("report_meta")

    # 一次性：无论成败都清空待发态，防止验证码重复消费
    session_context.pop("pending_email_verification", None)

    if not recipient or not report_id or not pdf_path:
        return _email_flow_response(
            sid,
            reply="会话状态已过期，请重新发起邮件发送。",
            followups=["重新生成报告", "生成行业趋势风控报告"],
        )

    try:
        await run_blocking(
            verification_service.consume_code, recipient, "send_email", (query or "").strip()
        )
    except ValueError as exc:
        return _email_flow_response(
            sid,
            reply=f"验证码校验失败：{exc}。",
            followups=["重新发送验证码", "从报告中心发送"],
        )

    try:
        await email_service.send_report_to(
            recipient, title, Path(pdf_path), report_id=report_id, identity=owner
        )
    except RuntimeError as exc:
        return _email_flow_response(
            sid,
            reply=f"验证码通过，但邮件发送失败：{exc}。",
            followups=["重新发送验证码", "从报告中心发送"],
        )

    try:
        await run_blocking(
            trusted_email_service.add_trusted_email, owner, recipient, "verified"
        )
    except Exception as exc:
        logger.debug("auto-trust after dialog verify failed: %s", exc)

    return _email_flow_response(
        sid,
        reply=f"验证通过，报告已发送至 {recipient}。",
        followups=["下载报告核对", "切换欺诈场景再出一份"],
        report_meta=report_meta,
    )


async def _fetch_demo_subject(db: AsyncSession) -> dict | None:
    """演示企业：取清单第一家（脱敏名），不是静默默认——仅 switch_scope(use_demo) 时调用。"""
    from sqlalchemy import select

    from app.models.core_metrics import CoreMetrics

    row = (
        await db.execute(
            select(
                CoreMetrics.enterprise_id,
                CoreMetrics.display_name,
                CoreMetrics.display_label,
            ).order_by(CoreMetrics.enterprise_id).limit(1)
        )
    ).first()
    if not row:
        return None
    return {
        "enterprise_id": row[0],
        "display_name": row[1] or row[2] or "企业1",
    }


def _attach_ui(result: dict, dialogue_state: dict, *, sample_count: int | None = None) -> dict:
    from app.services import scope_state as ss

    ui = ss.ui_bundle(dialogue_state, sample_count=sample_count)
    result["dialogue_state"] = ss.state_public(dialogue_state)
    result["ui"] = {
        "welcome": ui["welcome"],
        "chips": ui["chips"],
        "scope_bar": ui["scope_bar"],
        "scenario_buttons": ui["scenario_buttons"],
    }
    data = result.setdefault("data", {})
    data["dialogue_state"] = result["dialogue_state"]
    data["ui"] = result["ui"]
    if not data.get("followup_items") and ui.get("chips"):
        data["followup_items"] = ui["chips"]
        data["followups"] = [c.get("label") for c in ui["chips"] if c.get("label")]
    return result


async def route_chat(
    db: AsyncSession,
    query: str,
    session_id: str | None = None,
    enterprise_id: str | None = None,
    user: dict | None = None,
    followup: dict | None = None,
) -> dict:
    from app.services import followup_items as fu
    from app.services import scope_state as ss

    owner = _owner_email(user) if user else None
    sid = await run_blocking(session_store.ensure_session_id, session_id, owner)
    session_context = (await run_blocking(session_store.get_session, sid)) or {}

    # 范围状态：唯一真源（不再用请求里的 enterprise_id 静默钉死个体）
    dialogue_state = ss.normalize_dialogue_state(
        {
            **(session_context.get("dialogue_state") or {}),
            "scope": (session_context.get("dialogue_state") or {}).get("scope")
            or session_context.get("scope"),
            "subject": (session_context.get("dialogue_state") or {}).get("subject")
            or session_context.get("subject"),
            "scenario": (session_context.get("dialogue_state") or {}).get("scenario")
            or session_context.get("scenario"),
            "inventory_focus": (session_context.get("dialogue_state") or {}).get("inventory_focus"),
            "enterprise_id": session_context.get("enterprise_id"),
        }
    )
    # 兼容：显式传入 enterprise_id 且当前 unbound → 视为「选中这家」切换（列表点选）
    if enterprise_id and dialogue_state.get("scope") == "unbound":
        dialogue_state = ss.switch_scope(
            dialogue_state,
            target="individual",
            subject={"enterprise_id": enterprise_id, "display_name": "选定企业"},
        )
    elif enterprise_id and dialogue_state.get("scope") == "individual":
        sub = dialogue_state.get("subject") or {}
        if sub.get("enterprise_id") != enterprise_id:
            dialogue_state = ss.switch_scope(
                dialogue_state,
                target="individual",
                subject={"enterprise_id": enterprise_id, "display_name": sub.get("display_name") or "选定企业"},
            )

    # P2 焦点回溯：检测「回到刚才那批/回到之前的」类查询
    if query and re.search(r"回到|刚才那批|之前的|上次.*行业|上次.*地区", query):
        recalled_ind = ss.resolve_focus_from_history(dialogue_state, "industry")
        recalled_prov = ss.resolve_focus_from_history(dialogue_state, "province")
        if recalled_ind or recalled_prov:
            if recalled_ind:
                dialogue_state = ss.merge_analysis_focus(dialogue_state, industry_l1=recalled_ind)
            if recalled_prov:
                dialogue_state = ss.merge_analysis_focus(dialogue_state, province=recalled_prov)
            logger.info("focus recall: industry=%s province=%s", recalled_ind, recalled_prov)

    # ── bootstrap：首屏只下发 state 派生 UI，不算数 ──
    if followup and isinstance(followup, dict) and followup.get("type") == "bootstrap":
        ui = ss.ui_bundle(dialogue_state)
        await run_blocking(
            session_store.store_session,
            sid,
            intent="bootstrap",
            function="general",
            query="bootstrap",
            owner=owner,
            reply=ui["welcome"],
            followups=fu.labels_of(ui["chips"]),
            dialogue_state=dialogue_state,
        )
        return _attach_ui(
            {
                "reply": ui["welcome"],
                "reply_source": "template",
                "analysis_mode": "rule",
                "parse_source": "bootstrap",
                "intent": "bootstrap",
                "function": "general",
                "session_id": sid,
                "data": {
                    "followups": fu.labels_of(ui["chips"]),
                    "followup_items": ui["chips"],
                    "claims": [],
                    "evidence_hidden": True,
                },
            },
            dialogue_state,
        )

    # ── switch_scope：显式切换范围 ──
    if followup and isinstance(followup, dict) and followup.get("type") == "switch_scope":
        params = followup.get("params") if isinstance(followup.get("params"), dict) else {}
        target = str(followup.get("target") or params.get("target") or "").strip()
        if params.get("open_picker"):
            ui = ss.ui_bundle(dialogue_state)
            return _attach_ui(
                {
                    "reply": "请从右侧列表点选一家企业；选中后我会把范围切到该个体。",
                    "reply_source": "template",
                    "parse_source": "switch_scope",
                    "session_id": sid,
                    "data": {
                        "followups": fu.labels_of(ui["chips"]),
                        "followup_items": ui["chips"],
                        "claims": [],
                        "open_picker": True,
                        "evidence_hidden": True,
                    },
                },
                dialogue_state,
            )
        subject = None
        if target == "individual":
            if params.get("use_demo"):
                subject = await _fetch_demo_subject(db)
                if not subject:
                    return _attach_ui(
                        {
                            "reply": "暂无可用演示企业，请先接入数据或从列表选择。",
                            "reply_source": "template",
                            "parse_source": "switch_scope",
                            "session_id": sid,
                            "data": {"followup_items": ss.unbound_entry_items(), "claims": []},
                        },
                        dialogue_state,
                    )
            elif params.get("enterprise_id"):
                subject = {
                    "enterprise_id": params["enterprise_id"],
                    "display_name": params.get("display_name") or "选定企业",
                }
            elif (dialogue_state.get("subject") or {}).get("enterprise_id"):
                subject = dialogue_state["subject"]
            else:
                return _attach_ui(
                    {
                        "reply": "请指定要分析的企业（试用演示或从列表选）。",
                        "reply_source": "template",
                        "parse_source": "switch_scope",
                        "session_id": sid,
                        "data": {"followup_items": ss.unbound_entry_items(), "claims": []},
                    },
                    dialogue_state,
                )
        try:
            dialogue_state = ss.switch_scope(dialogue_state, target=target, subject=subject)
        except ValueError as exc:
            return _attach_ui(
                {
                    "reply": f"无法切换范围：{exc}",
                    "reply_source": "template",
                    "session_id": sid,
                    "data": {"claims": [], "followup_items": ss.unbound_entry_items()},
                },
                dialogue_state,
            )
        ui = ss.ui_bundle(dialogue_state)
        pending_q = (params.get("pending_query") or "").strip()
        # 「看全库」chip ≡ 范围清单：切到 cohort 后报真实库存（不弃权）
        if target == "cohort" and not pending_q:
            from app.services import inventory_scope as inv

            inv_out = await inv.inventory_answer(
                db, dialogue_state, ask_kind="overview"
            )
            items = inv_out.get("followup_items") or ss.unbound_entry_items()
            reply = inv_out.get("reply") or ui["welcome"]
            await run_blocking(
                session_store.store_session,
                sid,
                intent="negotiate_scope",
                function="inventory",
                query=followup.get("label") or "看全库",
                owner=owner,
                reply=reply,
                followups=fu.labels_of(items),
                dialogue_state=dialogue_state,
            )
            return _attach_ui(
                {
                    "reply": reply,
                    "reply_source": "template",
                    "parse_source": "negotiate_scope",
                    "intent": "negotiate_scope",
                    "function": "inventory",
                    "session_id": sid,
                    "data": {
                        "followups": fu.labels_of(items),
                        "followup_items": items,
                        "claims": claims_to_dict(inv_out.get("claims") or []),
                        "evidence_hidden": True,
                        "slice": inv_out.get("meta") or {},
                    },
                },
                dialogue_state,
                sample_count=inv_out.get("sample_count"),
            )
        await run_blocking(
            session_store.store_session,
            sid,
            intent=f"switch_scope_{target}",
            function="general",
            query=followup.get("label") or f"切换到{target}",
            owner=owner,
            reply=ui["welcome"],
            followups=fu.labels_of(ui["chips"]),
            dialogue_state=dialogue_state,
            enterprise_id=(dialogue_state.get("subject") or {}).get("enterprise_id"),
        )
        if pending_q:
            # 切完范围后立刻回答原问句
            return await route_chat(
                db,
                pending_q,
                session_id=sid,
                user=user,
                followup=None,
            )
        return _attach_ui(
            {
                "reply": ui["welcome"],
                "reply_source": "template",
                "parse_source": "switch_scope",
                "intent": f"switch_scope_{target}",
                "function": "general",
                "session_id": sid,
                "enterprise_id": (dialogue_state.get("subject") or {}).get("enterprise_id"),
                "data": {
                    "followups": fu.labels_of(ui["chips"]),
                    "followup_items": ui["chips"],
                    "claims": [],
                    "evidence_hidden": True,
                },
            },
            dialogue_state,
        )

    # ── 刀 1：结构化下钻（不把建议句当新 query 复读）──
    if followup and isinstance(followup, dict) and followup.get("type") == "drilldown":
        # 下钻要求 cohort 或已有 active_conclusion；无则反问
        if dialogue_state.get("scope") == "individual" and not session_context.get("active_conclusion"):
            resolved = ss.resolve_scope("哪里可疑要查？", dialogue_state)
            if resolved["status"] != "ok":
                pass
        drill = await fu.run_drilldown(
            db,
            op=str(followup.get("op") or ""),
            claim_id=followup.get("claim_id"),
            params=followup.get("params") if isinstance(followup.get("params"), dict) else {},
            session_context=session_context,
        )
        claims = drill.get("claims") or []
        followup_items = drill.get("followup_items") or fu.build_default_followups()
        followups = fu.labels_of(followup_items)
        meta = drill.get("meta") or {}
        function = meta.get("function") or "fraud"
        dimension = "signal"
        intent = f"drilldown_{followup.get('op')}"
        industry_l1 = None
        province = None
        sq = None
        report_meta = None
        if not drill.get("ok"):
            reply = drill.get("reply") or "下钻失败。"
            reply_source = "template"
        else:
            reply, bundle, reply_source = await llm_reply.generate_claim_reply(
                followup.get("label") or query or "下钻",
                claims,
                followups,
                report_hint=None,
            )
            if not (reply or "").strip():
                reply = llm_reply._template_from_claims(
                    claims, followups, with_prefix=False, report_hint=None, query=query
                )
                reply_source = "template"
            # P0 硬闸门：drilldown 路径同样过闸（含空 allowed）
            from app.services.hallucination_guard import apply_chat_hallucination_guard

            reply, _, followups = apply_chat_hallucination_guard(
                reply, claims, report_hint=None, followups=followups
            )
            if not (reply or "").strip():
                reply = llm_reply._ensure_reply("")
        from app.services.chart_payloads import normalize_meta_charts

        meta = normalize_meta_charts(meta or {})
        charts = meta.get("charts")
        conclusion_id = await run_blocking(
            conclusion_store.save_conclusion,
            session_id=sid,
            function=function,
            dimension=dimension,
            claims=claims,
            followups=followups,
            evidence_hidden=True,
            meta=meta,
        )
        active = {
            "claim_id": followup.get("claim_id") or "c_fraud_flagged",
            "meta": {
                "flagged_count": meta.get("flagged_count"),
                "sample_count": meta.get("sample_count"),
                "signal_counts": meta.get("signal_counts"),
                "flagged_firms": meta.get("flagged_firms") or meta.get("top_flags"),
                "top_flags": meta.get("top_flags"),
                "function": "fraud",
            },
        }
        # 下钻成功时切到 cohort（舞弊名单是群体切片）
        if drill.get("ok"):
            dialogue_state = ss.switch_scope(dialogue_state, target="cohort")
        await run_blocking(
            session_store.store_session,
            sid,
            intent=intent,
            function=function,
            dimension=dimension,
            query=followup.get("label") or query,
            conclusion_id=conclusion_id,
            owner=owner,
            reply=reply,
            followups=followups,
            active_conclusion=active,
            dialogue_state=dialogue_state,
        )
        return _attach_ui(
            {
                "reply": reply,
                "reply_source": reply_source,
                "analysis_mode": "rule",
                "parse_source": "drilldown",
                "judgment_modes": {"analysis": "rule", "parse": "drilldown", "narration": reply_source},
                "intent": intent,
                "function": function,
                "dimension": dimension,
                "session_id": sid,
                "conclusion_id": conclusion_id,
                "charts": charts,
                "data": {
                    "function": function,
                    "dimension": dimension,
                    "claims": claims_to_dict(claims),
                    "followups": followups,
                    "followup_items": followup_items,
                    "conclusion_id": conclusion_id,
                    "evidence_hidden": True,
                    "actions": [],
                    "slice": meta,
                },
            },
            dialogue_state,
        )

    # action 类型不应打到后端复读；若误传，直接返回提示
    if followup and isinstance(followup, dict) and followup.get("type") == "action":
        hint = ((followup.get("params") or {}) if isinstance(followup.get("params"), dict) else {}).get(
            "hint"
        ) or "这是人工核查动作，请按名单自行调证；系统不会复述为新的分析结论。"
        items = fu.build_fraud_followups((session_context.get("active_conclusion") or {}).get("meta") or {})
        return _attach_ui(
            {
                "reply": hint,
                "reply_source": "template",
                "analysis_mode": "rule",
                "parse_source": "action",
                "session_id": sid,
                "data": {
                    "followups": fu.labels_of(items),
                    "followup_items": items,
                    "claims": [],
                    "evidence_hidden": True,
                },
            },
            dialogue_state,
        )

    # ── DialogAct：先判 act，再分发（唯一硬性顺序）──
    from app.services import dialog_act as da
    from app.services import inventory_scope as inv

    classify_state = {
        **dialogue_state,
        "custom_report": session_context.get("custom_report"),
    }
    # 多意图拼句（可继续追问：A；B；C）→ 请选一项，禁止合成假 drill
    if not (followup and isinstance(followup, dict) and followup.get("type") in (
        "dialog_act", "drilldown", "action", "navigate", "switch_scope", "bootstrap",
    )):
        multi_parts = da.split_multi_intent(query or "")
        if multi_parts:
            clar = da.multi_intent_clarify(multi_parts)
            items = clar["followup_items"]
            await run_blocking(
                session_store.store_session,
                sid,
                intent="multi_intent",
                function="general",
                query=query,
                owner=owner,
                reply=clar["reply"],
                followups=fu.labels_of(items),
                dialogue_state=dialogue_state,
            )
            return _attach_ui(
                {
                    "reply": clar["reply"],
                    "reply_source": "template",
                    "parse_source": "multi_intent",
                    "intent": "multi_intent",
                    "function": "general",
                    "session_id": sid,
                    "data": {
                        "followups": fu.labels_of(items),
                        "followup_items": items,
                        "claims": [],
                        "dialog_act": clar.get("dialog_act"),
                    },
                },
                dialogue_state,
            )

    act = da.from_followup(followup)
    if act is None:
        act = await da.classify(query, classify_state)
    else:
        act = da.merge_inventory_focus(act, classify_state)

    # M1 弃权三态：can_answer=False 时提前返回
    if not act.can_answer:
        cq = da.get_clarify_question(act)
        if cq:
            # clarify：反问用户
            return _attach_ui(
                {
                    "reply": cq,
                    "reply_source": "template",
                    "parse_source": "clarify",
                    "intent": "clarify",
                    "function": "general",
                    "session_id": sid,
                    "data": {"claims": [], "followups": [], "dialog_act": act.model_dump()},
                },
                dialogue_state,
            )
        else:
            # abstain：弃权 + 引导回财税风控
            abstain_reply = "这个问题超出了我的数据范围。我可以帮你查询企业的税务健康、经营真实性、发票舞弊、风险预警等。请问想了解哪方面？"
            return _attach_ui(
                {
                    "reply": abstain_reply,
                    "reply_source": "template",
                    "parse_source": "abstain",
                    "intent": "abstain",
                    "function": "general",
                    "session_id": sid,
                    "data": {"claims": [], "followups": [], "dialog_act": act.model_dump()},
                },
                dialogue_state,
            )

    # 寒暄：短应答 + 入口 chips，不进分析门禁
    if act.act == "meta_session" and da.looks_greeting(query or ""):
        ui = ss.ui_bundle(dialogue_state)
        items = ui.get("chips") or ss.unbound_entry_items()
        scope = dialogue_state.get("scope") or "unbound"
        if scope == "individual":
            name = (dialogue_state.get("subject") or {}).get("display_name") or "当前企业"
            reply = f"你好。当前在看「{name}」。想继续问风险，或换一家 / 看全库都可以。"
        elif scope == "cohort":
            focus = dialogue_state.get("analysis_focus") or dialogue_state.get("inventory_focus") or {}
            ind = focus.get("industry_l1") or "全库群体"
            reply = f"你好。当前群体焦点是「{ind}」。可以直接问趋势、预警或生成报告。"
        else:
            reply = "你好。可以先看能分析哪些企业，或试用演示 / 看全库群体。"
        await run_blocking(
            session_store.store_session,
            sid,
            intent="meta_greeting",
            function="general",
            query=query,
            owner=owner,
            reply=reply,
            followups=fu.labels_of(items),
            dialogue_state=dialogue_state,
        )
        return _attach_ui(
            {
                "reply": reply,
                "reply_source": "template",
                "parse_source": "meta_greeting",
                "intent": "meta_greeting",
                "function": "general",
                "session_id": sid,
                "data": {
                    "followups": fu.labels_of(items),
                    "followup_items": items,
                    "claims": [],
                    "dialog_act": act.model_dump(),
                },
            },
            dialogue_state,
        )

    # 定制报告：与协商/分析同级一等能力
    if act.act == "custom_report":
        return await _route_custom_report(
            db, query or "我要定制报告", sid, user=user, session_context=session_context
        )

    # 低置信 / 乱答：反问澄清，不停机、不甩 FAQ
    if da.needs_clarify(act) and not (followup and followup.get("type") in ("dialog_act", "query")):
        clar = da.clarify_payload(act)
        items = clar["followup_items"]
        await run_blocking(
            session_store.store_session,
            sid,
            intent="clarify",
            function="general",
            query=query,
            owner=owner,
            reply=clar["reply"],
            followups=fu.labels_of(items),
            dialogue_state=dialogue_state,
        )
        return _attach_ui(
            {
                "reply": clar["reply"],
                "reply_source": "template",
                "parse_source": "clarify",
                "intent": "clarify",
                "function": "general",
                "session_id": sid,
                "data": {
                    "followups": fu.labels_of(items),
                    "followup_items": items,
                    "claims": [],
                    "evidence_hidden": True,
                    "dialog_act": act.model_dump(),
                },
            },
            dialogue_state,
        )

    # negotiate_scope：按 ask_kind/filters 答这一问（数字从引擎，不弃权）
    if act.act == "negotiate_scope":
        inv_out = await inv.inventory_answer(
            db,
            dialogue_state,
            ask_kind=act.ask_kind or "overview",
            industry_l1=act.industry_l1,
            province=act.province,
        )
        if act.scope_target == "cohort":
            dialogue_state = ss.switch_scope(dialogue_state, target="cohort")
        if inv_out.get("inventory_focus"):
            dialogue_state = {**dialogue_state, "inventory_focus": inv_out["inventory_focus"]}
        elif (act.ask_kind or "overview") == "overview":
            dialogue_state = {**dialogue_state, "inventory_focus": None}
        items = inv_out.get("followup_items") or ss.unbound_entry_items()
        reply = inv_out.get("reply") or ""
        await run_blocking(
            session_store.store_session,
            sid,
            intent="negotiate_scope",
            function="inventory",
            query=query or "negotiate_scope",
            owner=owner,
            reply=reply,
            followups=fu.labels_of(items),
            dialogue_state=dialogue_state,
        )
        return _attach_ui(
            {
                "reply": reply,
                "reply_source": "template",
                "parse_source": "negotiate_scope",
                "intent": "negotiate_scope",
                "function": "inventory",
                "session_id": sid,
                "data": {
                    "followups": fu.labels_of(items),
                    "followup_items": items,
                    "claims": claims_to_dict(inv_out.get("claims") or []),
                    "evidence_hidden": True,
                    "dialog_act": act.model_dump(),
                    "slice": inv_out.get("meta") or {},
                },
            },
            dialogue_state,
            sample_count=inv_out.get("sample_count"),
        )

    # bind_subject：解析 subject_ref → 切 scope，有场景则续答分析
    if act.act == "bind_subject":
        cur = (dialogue_state.get("subject") or {}).get("enterprise_id")
        subject = await inv.resolve_subject_ref(db, act.subject_ref, current_eid=cur)
        if not subject:
            items = ss.unbound_entry_items()
            reply = "暂时找不到可绑定的企业，请试用演示、从列表选，或先问能分析哪些。"
            return _attach_ui(
                {
                    "reply": reply,
                    "reply_source": "template",
                    "parse_source": "bind_subject",
                    "session_id": sid,
                    "data": {
                        "followups": fu.labels_of(items),
                        "followup_items": items,
                        "claims": [],
                        "dialog_act": act.model_dump(),
                    },
                },
                dialogue_state,
            )
        dialogue_state = ss.switch_scope(dialogue_state, target="individual", subject=subject)
        if act.scenario:
            dialogue_state = {**dialogue_state, "scenario": act.scenario}
            # 续答：把原问句当 analyze 再跑一轮
            return await route_chat(
                db,
                query or f"{subject.get('display_name')}风险怎么样",
                session_id=sid,
                user=user,
                followup={
                    "type": "dialog_act",
                    "label": query or "继续分析",
                    "params": {
                        "act": "analyze",
                        "scenario": act.scenario,
                        "scope_target": "individual",
                        "confidence": 1.0,
                    },
                },
            )
        ui = ss.ui_bundle(dialogue_state)
        await run_blocking(
            session_store.store_session,
            sid,
            intent="bind_subject",
            function="general",
            query=query or act.subject_ref or "bind",
            owner=owner,
            reply=ui["welcome"],
            followups=fu.labels_of(ui["chips"]),
            dialogue_state=dialogue_state,
            enterprise_id=subject.get("enterprise_id"),
        )
        return _attach_ui(
            {
                "reply": ui["welcome"],
                "reply_source": "template",
                "parse_source": "bind_subject",
                "intent": "bind_subject",
                "function": "general",
                "session_id": sid,
                "enterprise_id": subject.get("enterprise_id"),
                "data": {
                    "followups": fu.labels_of(ui["chips"]),
                    "followup_items": ui["chips"],
                    "claims": [],
                    "evidence_hidden": True,
                    "dialog_act": act.model_dump(),
                },
            },
            dialogue_state,
        )

    # meta_session：读 state，不跑分析
    if act.act == "meta_session":
        want_synthesis = bool(
            re.search(r"帮我综合|综合一下|汇总这几轮|会话综合", query or "")
        ) or bool(re.search(r"帮我综合|综合一下|汇总这几轮|会话综合", (followup or {}).get("label") or ""))
        if want_synthesis:
            # 交给后续个体/群体路径开 synthesis；先确保有范围
            act = da.DialogAct(
                act="analyze",
                scope_target="cohort" if dialogue_state.get("scope") == "cohort" else (
                    "individual" if dialogue_state.get("scope") == "individual" else None
                ),
                confidence=1.0,
            )
            # fall through to analyze after setting flag
            pass
        else:
            scope = dialogue_state.get("scope") or "unbound"
            sub = dialogue_state.get("subject") or {}
            name = sub.get("display_name")
            if scope == "individual" and name:
                reply = f"当前在看个体「{name}」。可以问能贷、信用、不对劲或可疑；也可换一家或看全库。"
            elif scope == "cohort":
                reply = "当前是全库群体视角。可以问哪里信号最多、按行业拆；若要问「这家」，请先选一家。"
            else:
                reply = "还没选定范围。你可以问能分析哪些企业，或试用演示 / 列表选 / 看全库。"
            items = ss.ui_bundle(dialogue_state)["chips"]
            await run_blocking(
                session_store.store_session,
                sid,
                intent="meta_session",
                function="general",
                query=query or "meta",
                owner=owner,
                reply=reply,
                followups=fu.labels_of(items),
                dialogue_state=dialogue_state,
            )
            return _attach_ui(
                {
                    "reply": reply,
                    "reply_source": "template",
                    "parse_source": "meta_session",
                    "intent": "meta_session",
                    "session_id": sid,
                    "data": {
                        "followups": fu.labels_of(items),
                        "followup_items": items,
                        "claims": [],
                        "dialog_act": act.model_dump(),
                    },
                },
                dialogue_state,
            )

    # product_faq：收窄 FAQ，不抢协商
    if act.act == "product_faq":
        from app.services.faq_kb import build_faq_claims

        faq_claims, faq_meta = build_faq_claims(query or "")
        items = fu.build_faq_followups()
        # 出口带上范围协商，避免 FAQ 闭环
        items = [
            fu.item(
                type="dialog_act",
                label="我能分析哪些企业？",
                params={"act": "negotiate_scope", "confidence": 1.0},
            ),
            *items,
        ][:6]
        reply = faq_claims[0].claim if faq_claims else "暂无对应说明。"
        await run_blocking(
            session_store.store_session,
            sid,
            intent="product_faq",
            function="faq",
            query=query or "faq",
            owner=owner,
            reply=reply,
            followups=fu.labels_of(items),
            dialogue_state=dialogue_state,
        )
        return _attach_ui(
            {
                "reply": reply,
                "reply_source": "template",
                "parse_source": "product_faq",
                "intent": "product_faq",
                "function": "faq",
                "session_id": sid,
                "data": {
                    "followups": fu.labels_of(items),
                    "followup_items": items,
                    "claims": claims_to_dict(faq_claims),
                    "actions": faq_meta.get("actions") or [],
                    "dialog_act": act.model_dump(),
                },
            },
            dialogue_state,
        )

    # drill：仅结构化 drilldown 且 op∈DRILLDOWN_OPS；否则降为 analyze（禁止假下钻）
    if act.act == "drill":
        op = (act.drill_op or (followup or {}).get("op") if followup else None) or ""
        structured = bool(followup and followup.get("type") == "drilldown")
        if structured and op in fu.DRILLDOWN_OPS:
            # 已有合法 drilldown followup：上方 early return 已处理；此处不应再合成
            pass
        else:
            # 继续分析路径：真实性/地区/趋势等
            act = da.DialogAct(
                act="analyze",
                scenario=act.scenario or "warn",
                scope_target=act.scope_target or "cohort",
                industry_l1=act.industry_l1,
                province=act.province,
                confidence=max(float(act.confidence or 0.7), 0.7),
            )

    # analyze / drill：仅此时跑 resolve_scope 门禁（R2）
    want_synthesis = bool(re.search(r"帮我综合|综合一下|汇总这几轮|会话综合", query or ""))
    if act.act == "meta_session" and want_synthesis:
        want_synthesis = True

    required = act.scope_target
    if required is None and act.act in ("analyze", "drill"):
        # 槽位未填：沿用当前 scope；unbound 则按场景默认个体，无场景则反问
        cur = dialogue_state.get("scope") or "unbound"
        if cur in ("individual", "cohort"):
            required = cur
        elif act.scenario in ("loan", "rating", "warn", "audit"):
            required = "individual"
        else:
            required = None

    if act.act in ("analyze", "drill"):
        resolved = ss.resolve_scope(
            query,
            dialogue_state,
            followup=followup,
            required=required,
            scenario=act.scenario,
            use_infer=False,
        )
    else:
        resolved = {"status": "ok", "state": dialogue_state, "scenario": act.scenario}

    if resolved.get("auto_switched"):
        dialogue_state = resolved["state"]
    if resolved["status"] in ("ask_bind", "confirm_switch"):
        items = resolved.get("followup_items") or ss.unbound_entry_items()
        for it in items:
            if it.get("type") == "switch_scope" and (it.get("params") or {}).get("use_demo"):
                it.setdefault("params", {})["pending_query"] = query
        await run_blocking(
            session_store.store_session,
            sid,
            intent=f"scope_{resolved['status']}",
            function="general",
            query=query,
            owner=owner,
            reply=resolved.get("reply"),
            followups=fu.labels_of(items),
            dialogue_state=dialogue_state,
        )
        return _attach_ui(
            {
                "reply": resolved.get("reply") or "请先选择分析范围。",
                "reply_source": "template",
                "parse_source": "scope_guard",
                "intent": f"scope_{resolved['status']}",
                "function": "general",
                "session_id": sid,
                "data": {
                    "followups": fu.labels_of(items),
                    "followup_items": items,
                    "claims": [],
                    "evidence_hidden": True,
                    "scope_guard": resolved["status"],
                    "dialog_act": act.model_dump(),
                },
            },
            dialogue_state,
        )

    dialogue_state = resolved["state"]
    scenario = act.scenario or resolved.get("scenario") or dialogue_state.get("scenario")
    if scenario:
        dialogue_state = {**dialogue_state, "scenario": scenario}

    # 邮件验证码回复拦截
    pending = session_context.get("pending_email_verification")
    if pending and dialogue_state.get("scope") != "individual" and _VERIFY_CODE_RE.fullmatch((query or "").strip()):
        return await _route_email_verify_code(
            db, sid, query, pending, user=user, session_context=session_context
        )

    report_meta: dict | None = None
    intent_result: IntentResult | None = None
    sq: SemanticQuery | None = None

    # 个体：按场景组织（R3），不再一律画像 dump
    if dialogue_state.get("scope") == "individual" and (dialogue_state.get("subject") or {}).get("enterprise_id"):
        enterprise_id = dialogue_state["subject"]["enterprise_id"]
        branch = await _route_enterprise(
            db, query, enterprise_id, user=user, scenario=scenario
        )
        claims = branch["claims"]
        followups = branch["followups"]
        meta = branch["meta"]
        function = branch["function"]
        dimension = branch["dimension"]
        intent = branch["intent"]
        report_meta = branch["report_meta"]
        industry_l1 = branch["industry_l1"]
        province = branch["province"]
        if want_synthesis:
            meta["include_synthesis"] = True
    else:
        # 全库 / 未绑定但问句不强制个体（FAQ 等）
        enterprise_id = None
        intent_result = intent_engine.recognize(query, session_context=session_context)
        function = intent_result.function
        dimension = intent_result.dimension
        intent = intent_result.intent
        industry_l1 = intent_result.industry_l1
        province = intent_result.province
        # 能力地图：act.tools 优先覆盖 function/dimension/filters（替代纯关键词）
        tool_slots = da.resolve_analyze_tools(act)
        if tool_slots.get("function"):
            function = tool_slots["function"]
            dimension = tool_slots.get("dimension") or dimension
            intent_result.function = function
            intent_result.dimension = dimension
            intent_result.intent = f"{function}_{dimension}"
            intent = intent_result.intent
        if tool_slots.get("industry_l1"):
            industry_l1 = tool_slots["industry_l1"]
            intent_result.industry_l1 = industry_l1
        if tool_slots.get("province"):
            province = tool_slots["province"]
            intent_result.province = province
        # DialogAct=analyze 时禁止落 general：按场景对齐引擎 function（根贯通）
        if act.act == "analyze" and intent_result.function == "general":
            _sc_fn = {
                "warn": ("signal", "signal"),
                "audit": ("fraud", "overall"),
                "loan": ("score", "overall"),
                "rating": ("score", "overall"),
            }
            mf, md = _sc_fn.get(act.scenario or "warn", ("signal", "signal"))
            intent_result.function = mf
            intent_result.dimension = md
            intent_result.intent = f"{mf}_{md}"
            function, dimension, intent = mf, md, intent_result.intent
        # DialogAct / 会话分析焦点 → 覆盖引擎槽位（根贯通，非补丁）
        if act.industry_l1:
            industry_l1 = act.industry_l1
            intent_result.industry_l1 = act.industry_l1
        if act.province:
            province = act.province
            intent_result.province = act.province
        expand_all = bool(
            re.search(r"各行业|全库|全样本|全部样本|看全部", query or "")
        )
        if not expand_all:
            af = dialogue_state.get("analysis_focus") or {}
            invf = dialogue_state.get("inventory_focus") or {}
            if not industry_l1:
                industry_l1 = af.get("industry_l1") or invf.get("industry_l1")
                if industry_l1:
                    intent_result.industry_l1 = industry_l1
            if not province:
                province = af.get("province") or invf.get("province")
                if province:
                    intent_result.province = province
        else:
            # 显式扩全库：清本轮行业焦点
            industry_l1 = None
            intent_result.industry_l1 = None

        # 定制报告
        custom_state = session_context.get("custom_report")
        if (custom_state and custom_state.get("active")) or function == "custom_report":
            return await _route_custom_report(db, query, sid, user=user, session_context=session_context)

        # analyze 路径禁止 FAQ 抢答（协商/分析已由 DialogAct 分流）
        faq_sq = None
        if act.act not in ("analyze", "drill"):
            faq_sq = semantic_query.detect_faq_or_methodology(query)

        if faq_sq is None and function in ("report", "email_report"):
            try:
                claims, followups, meta = await judgment_service.run_judgment(db, intent_result, sid)
            except Exception as exc:
                logger.warning("judgment failed, empty claims: %s", exc)
                claims = [
                    Claim(
                        claim="风控引擎暂时不可用，请稍后重试。",
                        value=ClaimValue(metric="error", number=None, unit=""),
                        trace=ClaimTrace(table="core_metrics", field="enterprise_id", query_id="Q_error"),
                        confidence="inferred",
                    )
                ]
                followups = judgment_service.DEFAULT_FOLLOWUPS["general"]
                meta = {"error": str(exc)}
        else:
            if faq_sq is not None:
                sq = faq_sq
            else:
                if llm_reply.llm_available():
                    try:
                        parsed = await llm_semantic_parser.parse_semantic_query(
                            query,
                            session_context=session_context,
                            dictionary=metric_registry.build_llm_dictionary(),
                        )
                        if parsed is not None:
                            sq = semantic_query.correct_semantic_query(parsed, session_context)
                            sq = semantic_query.prefer_trend_over_spurious_comparison(
                                sq, query, intent=intent_result
                            )
                            from app.schemas.semantic_query import QueryType as _QT

                            _analysis = {
                                "fraud",
                                "signal",
                                "score",
                                "authenticity",
                                "benchmark",
                                "trend",
                            }
                            # analyze/drill 动作下 LLM 不得改写成 FAQ（含「群体风险…然后呢」）
                            if sq.query_type in (_QT.faq, _QT.methodology) and (
                                intent_result.function in _analysis
                                or act.act in ("analyze", "drill")
                            ):
                                logger.info(
                                    "reject llm faq for analysis act=%s fn=%s q=%r",
                                    act.act,
                                    intent_result.function,
                                    query[:40],
                                )
                                sq = semantic_query.intent_to_semantic_query(intent_result)
                    except Exception as exc:
                        logger.debug("semantic parse failed: %s", exc)
                if sq is None:
                    sq = semantic_query.detect_rule_comparison(query) or semantic_query.intent_to_semantic_query(intent_result)
                    sq = semantic_query.prefer_trend_over_spurious_comparison(
                        sq, query, intent=intent_result
                    )

            prev_sq = semantic_query.semantic_query_from_dict(
                (session_context or {}).get("last_semantic_query")
            )
            if intent_engine.is_followup_query(query) and prev_sq is not None:
                sq = semantic_query.merge_followup(sq, prev_sq, query)

            intent_result.semantic_query = sq
            function = semantic_query.query_type_to_function(sq)
            dimension = semantic_query.query_type_to_dimension(sq)
            intent = f"{sq.query_type.value}_{function}"
            industry_l1 = (sq.filters.get("industry_l1") or [None])[0]
            province = (sq.filters.get("province") or [None])[0]

            # 红线 §2.2 多意图并行：act.tools ≥2 个合法工具时，并行执行并合并 claims
            multi_tool_plans = (
                da.resolve_all_analyze_tools(act)
                if act.act == "analyze" and len(act.tools or []) >= 2
                else []
            )

            async def _run_one_plan(plan: dict) -> tuple[list, list, dict]:
                """按单个 tool 计划构造 sq 子查询并跑引擎；失败返回空 claims。"""
                sub_ir = intent_engine.IntentResult(
                    function=plan["function"],
                    dimension=plan.get("dimension") or dimension,
                    industry_l1=plan.get("industry_l1") or industry_l1,
                    province=plan.get("province") or province,
                    raw_query=query or "",
                    intent=f"{plan['function']}_{plan.get('dimension') or dimension}",
                )
                try:
                    sub_sq = semantic_query.intent_to_semantic_query(sub_ir)
                    c, f, m = await judgment_service.run_semantic_query(
                        db, sub_sq, sid, intent=sub_ir
                    )
                    return c, f, m
                except Exception as exc:
                    logger.warning(
                        "multi-intent tool %s failed: %s", plan.get("function"), exc
                    )
                    return [], [], {}

            if len(multi_tool_plans) >= 2:
                # 并行执行所有工具计划（asyncio.gather）
                import asyncio as _asyncio

                results = await _asyncio.gather(
                    *[_run_one_plan(p) for p in multi_tool_plans]
                )
                merged_claims: list = []
                merged_followups: list = []
                merged_meta: dict = {"multi_intent": True, "tools": []}
                for plan, (c, f, m) in zip(multi_tool_plans, results):
                    merged_claims.extend(c or [])
                    for fu in f or []:
                        if fu and fu not in merged_followups:
                            merged_followups.append(fu)
                    merged_meta["tools"].append(
                        {
                            "function": plan.get("function"),
                            "dimension": plan.get("dimension"),
                            "claims_count": len(c or []),
                        }
                    )
                    if isinstance(m, dict):
                        # 保留首个非空 meta 的部分键（避免相互覆盖）
                        for k, v in m.items():
                            if k not in merged_meta and k not in ("multi_intent", "tools"):
                                merged_meta[k] = v

                run_single_intent_fallback = not merged_claims
                if not run_single_intent_fallback:
                    claims = merged_claims
                    # 仅在并行路径拿到非空 followups 时扩展；保留 followups 初值
                    if merged_followups:
                        # 与初值合并去重（保留原顺序）
                        seen: list[str] = []
                        for fu in list(followups or []) + merged_followups:
                            if fu and fu not in seen:
                                seen.append(fu)
                        followups = seen
                    meta = {**(meta if isinstance(meta, dict) else {}), **merged_meta}
            else:
                run_single_intent_fallback = True

            if run_single_intent_fallback:
                try:
                    claims, followups, meta = await judgment_service.run_semantic_query(
                        db, sq, sid, intent=intent_result
                    )
                except Exception as exc:
                    logger.warning("semantic judgment failed: %s", exc)
                    claims = [
                        Claim(
                            claim="风控引擎暂时不可用，请稍后重试。",
                            value=ClaimValue(metric="error", number=None, unit=""),
                            trace=ClaimTrace(table="core_metrics", field="enterprise_id", query_id="Q_error"),
                            confidence="inferred",
                        )
                    ]
                    followups = judgment_service.DEFAULT_FOLLOWUPS["general"]
                    meta = {"error": str(exc)}
            if want_synthesis:
                meta["include_synthesis"] = True
                # 再跑一遍带综合（轻量：仅标记，本轮已算完；综合留给显式入口）
                pass

    # 报告意图（切片）：须订阅鉴权；直接产出切片 PDF（保留覆盖度 claims）
    if function in ("report", "email_report"):
        denied = _subscription_denied_claim(user)
        if denied:
            claims = [denied]
            followups = ["升级定制后生成报告", "改问行业趋势或风险摘要"]
            meta = {**(meta if isinstance(meta, dict) else {}), "subscription_required": True}
        elif function == "report" and not has_scenario_keyword(query):
          # 通用「生成报告」且未指定场景：二选一入口（固定模板 vs AI 定制），不自动生成
          coverage_claims = list(claims)
          claims = coverage_claims + [
              Claim(
                  claim="你想用哪类服务？① 直接生成固定报告（财务/税务/发票舞弊/尽调/画像/总览 6 套模板）；② AI 定制报告（对话式，AI 判断风控场景并自由组合章节后自动生成）。",
                  value=ClaimValue(metric="report_paths", number=None, unit=""),
                  trace=ClaimTrace(
                      table="report_templates",
                      field="scenario",
                      query_id="Q_report_paths",
                  ),
                  confidence="computed",
                  evidence_chain=["scenario_selector=True", "custom_available=True"],
              )
          ]
          followups = ["我要定制报告", *_scoped_scenario_prompts()]
          meta["scenario_selector"] = True
          # R5：报告入口跟随当前 scope
          if dialogue_state.get("scope") == "individual":
              meta["actions"] = [
                  {"label": "生成该企业深度报告", "target": "/report?wizard=1"},
                  {"label": "AI 定制报告", "target": "/research?custom=1"},
              ]
          else:
              meta["actions"] = [
                  {"label": "直接生成固定报告（6 套模板）", "target": "/report?wizard=1"},
                  {"label": "AI 定制报告（对话式自由组合）", "target": "/research?custom=1"},
              ]
        else:
          coverage_claims = list(claims)
          try:
            from app.services.slice_report import generate_slice_report

            scenario_key = resolve_scenario(query=query)
            report_id, pdf_path, ctx = await generate_slice_report(
                db,
                scenario=scenario_key,
                session_id=sid,
                query=query,
                owner=_owner_email(user),
                industry_l1=industry_l1,
                province=province,
            )
            report_claims = [
                Claim(
                    claim=f"已生成《{ctx.get('title')}》，报告编号 {report_id}。",
                    value=ClaimValue(metric="report", number=None, unit=""),
                    trace=ClaimTrace(
                        table="conclusion_store",
                        field="claims",
                        query_id="Q_slice_report",
                    ),
                    confidence="computed",
                    evidence_chain=[
                        f"scenario={ctx.get('scenario')}",
                        f"chapters={len(ctx.get('chapters') or [])}",
                        f"validation_ok={(ctx.get('validation') or {}).get('ok')}",
                    ],
                )
            ]
            if function == "email_report":
                recipient = intent_result.recipient if intent_result else None
                user_email = (
                    ((user or {}).get("email") or (user or {}).get("sub") or "")
                ).strip().lower()
                recv = (recipient or "").strip().lower()
                if recv and (recv == user_email or trusted_email_service.is_trusted(user_email, recv)):
                    # 受信直达（注册邮箱 / 已验证邮箱）
                    if email_service.is_configured():
                        try:
                            await email_service.send_report_to(
                                recv,
                                ctx.get("title") or "风控报告",
                                Path(pdf_path),
                                report_id=report_id,
                                identity=user_email,
                            )
                            report_claims.append(
                                Claim(
                                    claim=f"报告已发送至 {recv}。",
                                    value=ClaimValue(metric="email_sent", number=None, unit=""),
                                    trace=ClaimTrace(
                                        table="conclusion_store",
                                        field="claims",
                                        query_id="Q_email_report",
                                    ),
                                    confidence="computed",
                                    evidence_chain=[f"recipient={recv}"],
                                )
                            )
                            meta["email_sent"] = True
                        except RuntimeError as exc:
                            logger.warning("email send failed: %s", exc)
                            report_claims.append(
                                Claim(
                                    claim=f"报告已生成，但邮件发送失败：{exc}。请从报告中心下载后手动发送。",
                                    value=ClaimValue(metric="email_error", number=None, unit=""),
                                    trace=ClaimTrace(
                                        table="conclusion_store",
                                        field="claims",
                                        query_id="Q_email_report_fail",
                                    ),
                                    confidence="inferred",
                                )
                            )
                            meta["email_error"] = str(exc)
                    else:
                        report_claims.append(
                            Claim(
                                claim=(
                                    f"报告已生成。邮件服务未配置（{email_service.NOT_CONFIGURED_MSG}），"
                                    f"无法发送至 {recv}，请从报告中心下载。"
                                ),
                                value=ClaimValue(metric="email_skipped", number=None, unit=""),
                                trace=ClaimTrace(
                                    table="conclusion_store",
                                    field="claims",
                                    query_id="Q_email_not_configured",
                                ),
                                confidence="inferred",
                            )
                        )
                elif recv and email_service.is_configured():
                    # 非受信：发验证码，对话内引导输入 6 位码
                    try:
                        code_info = await run_blocking(
                            verification_service.issue_code, recv, "send_email"
                        )
                        await run_blocking(
                            email_service.send_verification_code, recv, code_info["code"], 10
                        )
                        session_context["pending_email_verification"] = {
                            "recipient": recv,
                            "user_email": user_email,
                            "report_id": report_id,
                            "title": ctx.get("title") or "风控报告",
                            "pdf_path": str(pdf_path),
                            "report_meta": {
                                "report_id": report_id,
                                "download_url": f"/api/v1/report/{report_id}/download",
                                "title": ctx.get("title"),
                                "validation": ctx.get("validation"),
                            },
                        }
                        report_claims.append(
                            Claim(
                                claim=(
                                    f"报告已生成。收件邮箱 {recv} 尚未受信，已发送验证码"
                                    f"（10 分钟内有效），请回复 6 位验证码完成发送。"
                                ),
                                value=ClaimValue(metric="email_verify", number=None, unit=""),
                                trace=ClaimTrace(
                                    table="conclusion_store",
                                    field="claims",
                                    query_id="Q_email_report_verify",
                                ),
                                confidence="computed",
                                evidence_chain=[f"recipient={recv}"],
                            )
                        )
                        meta["email_verify"] = True
                    except ValueError as exc:
                        # 冷却 / 发送频率超限
                        report_claims.append(
                            Claim(
                                claim=f"验证码发送失败：{exc}。",
                                value=ClaimValue(metric="email_error", number=None, unit=""),
                                trace=ClaimTrace(
                                    table="conclusion_store",
                                    field="claims",
                                    query_id="Q_email_report_verify_fail",
                                ),
                                confidence="inferred",
                            )
                        )
                        meta["email_error"] = str(exc)
                    except RuntimeError as exc:
                        report_claims.append(
                            Claim(
                                claim=f"验证码邮件发送失败：{exc}。",
                                value=ClaimValue(metric="email_error", number=None, unit=""),
                                trace=ClaimTrace(
                                    table="conclusion_store",
                                    field="claims",
                                    query_id="Q_email_report_verify_fail",
                                ),
                                confidence="inferred",
                            )
                        )
                        meta["email_error"] = str(exc)
                elif recv and not email_service.is_configured():
                    report_claims.append(
                        Claim(
                            claim=(
                                f"报告已生成。邮件服务未配置（{email_service.NOT_CONFIGURED_MSG}），"
                                f"无法发送至 {recv}，请从报告中心下载。"
                            ),
                            value=ClaimValue(metric="email_skipped", number=None, unit=""),
                            trace=ClaimTrace(
                                table="conclusion_store",
                                field="claims",
                                query_id="Q_email_not_configured",
                            ),
                            confidence="inferred",
                        )
                    )
                else:
                    report_claims.append(
                        Claim(
                            claim="报告已生成。未识别到收件邮箱，请补充如「发到 user@example.com」或从报告中心下载。",
                            value=ClaimValue(metric="email_skipped", number=None, unit=""),
                            trace=ClaimTrace(
                                table="conclusion_store",
                                field="claims",
                                query_id="Q_email_no_recipient",
                            ),
                            confidence="inferred",
                        )
                    )
            claims = coverage_claims + report_claims
            report_meta = {
                "report_id": report_id,
                "download_url": f"/api/v1/report/{report_id}/download",
                "title": ctx.get("title"),
                "validation": ctx.get("validation"),
            }
            followups = ["下载后核对数据说明", "切换欺诈场景再出一份", "继续追问行业趋势"]
            meta.update(report_meta)
          except PremiumReportLocked:
            claims = coverage_claims + [
                Claim(
                    claim="定制报告为付费功能，开发期已隔离，当前仅提供通用模板。可说「生成行业趋势风控报告」获取通用版。",
                    value=ClaimValue(metric="report_locked", number=None, unit=""),
                    trace=ClaimTrace(
                        table="conclusion_store",
                        field="claims",
                        query_id="Q_report_premium_locked",
                    ),
                    confidence="inferred",
                )
            ]
            meta["report_locked"] = True
            followups = ["生成行业趋势风控报告", "查看报告覆盖度", "分析行业趋势"]
          except Exception as exc:
            logger.warning("slice report failed: %s", exc)
            meta["report_error"] = str(exc)

    covered = await run_blocking(conclusion_store.covered_functions, sid) | {function}
    report_hint = None
    if enterprise_id and function != "report":
        report_hint = "可继续说「生成个体深度报告」导出该匿名样本的深度报告。"
    elif len(covered & {"trend", "authenticity", "fraud", "score", "benchmark", "signal"}) >= 3:
        report_hint = "当前会话覆盖度较好，可说「生成报告」产出组合风险报告。"

    # 刀 1：结构化 followup（FAQ 不再闭环；舞弊结论挂 drilldown/action/navigate）
    from app.services import followup_items as fu

    # 持久化分析焦点：cohort + 有切片时写入；显式「各行业/全库」则清除
    if dialogue_state.get("scope") == "cohort" or (act.scope_target == "cohort"):
        if re.search(r"各行业|全库|全样本|全部样本|看全部", query or ""):
            dialogue_state = ss.merge_analysis_focus(dialogue_state, clear=True)
        elif industry_l1 or province:
            dialogue_state = ss.merge_analysis_focus(
                dialogue_state, industry_l1=industry_l1, province=province
            )
        if isinstance(meta, dict):
            af = dialogue_state.get("analysis_focus") or {}
            if industry_l1:
                meta["industry_l1"] = industry_l1
            elif af.get("industry_l1"):
                meta["industry_l1"] = af.get("industry_l1")
            if province:
                meta["province"] = province
            elif af.get("province"):
                meta["province"] = af.get("province")

    enrich_meta = {
        **(meta or {}),
        "function": function,
        "query_type": (sq.query_type.value if sq else (meta or {}).get("query_type")),
        "industry_l1": industry_l1 or (meta or {}).get("industry_l1"),
        "province": province or (meta or {}).get("province"),
    }

    followup_items = fu.enrich_followups_for_meta(followups, enrich_meta)
    followups = fu.labels_of(followup_items)

    # M2：从 scenario 派生统一人格
    from app.services.persona import get_persona
    _scenario_for_persona = dialogue_state.get("scenario") or (meta or {}).get("scenario")
    _persona = get_persona(_scenario_for_persona)

    # ③ 通义点金（在 DeepSeek 校验润色之前；只解释，不直接拼进终态）
    financial_interp = None
    if claims and llm_reply.financial_llm_available():
        fi_context = {
            "industry_l1": industry_l1 or (meta or {}).get("industry_l1"),
            "scope": dialogue_state.get("scope") or "cohort",
            "scenario": _scenario_for_persona,
        }
        financial_interp = await llm_reply.generate_financial_interpretation(claims, fi_context)

    # ④ DeepSeek 校验润色：Claims + 金融因果参考 → 大白话
    reply, bundle, reply_source = await llm_reply.generate_claim_reply(
        query,
        claims,
        followups,
        report_hint=report_hint,
        persona=_persona,
        financial_interp=financial_interp,
    )
    if not (reply or "").strip():
        reply = llm_reply._template_from_claims(
            claims, followups, with_prefix=False, report_hint=report_hint, query=query
        )
        reply_source = "template"

    # ⑤ P0 硬闸门：对话终态 hallucination_guard（永不跳过，含空 allowed）
    from app.services.hallucination_guard import apply_chat_hallucination_guard

    reply, report_hint, followups = apply_chat_hallucination_guard(
        reply, claims, report_hint=report_hint, followups=followups
    )
    if not (reply or "").strip():
        reply = llm_reply._ensure_reply("")

    # 叙述层若改写了 followups，再规范化一次（去掉附录、FAQ 闭环）后二次过闸
    if bundle and getattr(bundle, "followups", None):
        followup_items = fu.enrich_followups_for_meta(list(bundle.followups), enrich_meta)
        followups = fu.labels_of(followup_items)
        _, _, followups = apply_chat_hallucination_guard(
            "", claims, report_hint=None, followups=followups
        )

    from app.services.chart_payloads import normalize_meta_charts

    meta = normalize_meta_charts(meta or {})
    charts = meta.get("charts")

    # synthesis 仅用于当轮展示，不写入 conclusion_store，避免多轮 headline 自污染
    persist_claims = without_synthesis_claims(claims)

    conclusion_id = await run_blocking(
        conclusion_store.save_conclusion,
        session_id=sid,
        function=function,
        dimension=dimension,
        claims=persist_claims,
        followups=list(followups),
        evidence_hidden=True,
        meta={
            "intent": intent,
            "industry_l1": industry_l1,
            "province": province,
            "charts": charts,
            **{k: v for k, v in meta.items() if k != "charts"},
        },
    )

    active_conclusion = None
    if int(meta.get("flagged_count") or 0) > 0 or meta.get("flagged_firms") or meta.get("top_flags"):
        active_conclusion = {
            "claim_id": "c_fraud_flagged",
            "meta": {
                "flagged_count": meta.get("flagged_count"),
                "sample_count": meta.get("sample_count"),
                "signal_counts": meta.get("signal_counts"),
                "flagged_firms": meta.get("flagged_firms") or meta.get("top_flags"),
                "top_flags": meta.get("top_flags"),
                "function": "fraud",
            },
        }

    await run_blocking(
        session_store.store_session,
        sid,
        intent=intent,
        function=function,
        dimension=dimension,
        industry_l1=industry_l1,
        province=province,
        enterprise_id=enterprise_id,
        query=query,
        conclusion_id=conclusion_id,
        semantic_query=semantic_query.semantic_query_to_dict(sq) if sq else None,
        owner=owner,
        reply=reply,
        followups=list(followups),
        active_conclusion=active_conclusion,
        dialogue_state=dialogue_state,
    )

    # 对话层：data 带 claims（含 trace）供前端/报告；reply 不含证据链
    data = {
        "function": function,
        "dimension": dimension,
        "query_type": sq.query_type.value if sq else None,
        "semantic_query": semantic_query.semantic_query_to_dict(sq) if sq else None,
        "industry_l1": industry_l1,
        "province": province,
        "enterprise_id": enterprise_id,
        "claims": claims_to_dict(claims),
        "followups": list(followups),
        "followup_items": followup_items,
        "conclusion_id": conclusion_id,
        "evidence_hidden": True,
        "coverage": sorted(await run_blocking(conclusion_store.covered_functions, sid)),
        "report_hint": report_hint,
        "actions": (meta or {}).get("actions", []),
        "slice": {k: v for k, v in meta.items() if k not in ("charts", "flagged_firms")},
    }
    if report_meta:
        data["report"] = report_meta

    logger.info(
        "route_chat fn=%s dim=%s scope=%s claims=%d reply[:120]=%r",
        function,
        dimension,
        (dialogue_state or {}).get("scope"),
        len(claims),
        reply[:120],
    )

    return _attach_ui(
        {
            "reply": reply,
            "reply_source": reply_source,
            "analysis_mode": "rule",
            "parse_source": (sq.source if sq else "rule"),
            "judgment_modes": {
                "analysis": "rule",
                "parse": (sq.source if sq else "rule"),
                "narration": "llm" if reply_source == "llm" else "rule",
            },
            "intent": intent,
            "function": function,
            "dimension": dimension,
            "query_type": sq.query_type.value if sq else None,
            "enterprise_id": enterprise_id,
            "enterprise_label": meta.get("enterprise_label"),
            "data": data,
            "charts": charts,
            "session_id": sid,
            "conclusion_id": conclusion_id,
        },
        dialogue_state,
    )


# --- 兼容旧测试 ---
def _radar_chart(ent: dict) -> dict:
    from app.services.chart_payloads import enterprise_radar_chart

    return enterprise_radar_chart(ent)


def _bar_chart(items: list[dict], metric: str = "overall_score", title: str = "综合分") -> dict:
    from app.services.chart_payloads import normalize_chart_payload

    return normalize_chart_payload(
        {
            "shape": "categorical_distribution",
            "title": title,
            "data": {
                "labels": [
                    i.get("enterprise_name") or i.get("display_label") or i.get("industry_l1", "")
                    for i in items
                ],
                "series": [{"name": title, "values": [i.get(metric, 0) for i in items]}],
            },
        }
    )


def _missing_enterprise_message(intent: str) -> str:
    return "匿名切片模式请按行业/地区提问，例如：分析各行业的趋势走向"


def _unknown_enterprise_message() -> str:
    return "匿名切片模式不支持具名企业查询，请改问行业趋势、真实性或舞弊信号。"
