"""AI 对话路由：功能×维度意图 → 风控分析 → 结论（隐藏证据）→ 追问"""
from __future__ import annotations

import logging
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
)
from app.services.intent_engine import IntentResult, industry_l1_options
from app.services.judgment_service import without_synthesis_claims
from app.services.report_templates import (
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
    db: AsyncSession, query: str, enterprise_id: str, *, user: dict | None = None
) -> dict:
    """个体下钻：画像风控分析；「生成个体深度报告」时产出个体 PDF（脱敏：仅哈希 id）。"""
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
            out["followups"] = ["下载后核对附录数据说明", "继续追问同业基准", "回到个体画像"]
            out["report_meta"] = {
                "report_id": report_id,
                "download_url": f"/api/v1/report/{report_id}/download",
                "title": ctx.get("title"),
                "validation": ctx.get("validation"),
            }
            out["meta"] = {"enterprise_id": enterprise_id, "report_id": report_id}
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

    claims, meta = await judgment_service.build_enterprise_claims(db, enterprise_id)
    out["claims"] = claims
    out["meta"] = meta
    out["followups"] = judgment_service.derive_enterprise_followups(meta, claims)
    out["industry_l1"] = meta.get("industry_l1")
    out["province"] = meta.get("province")
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
    for fn, (title, _desc) in CUSTOM_CHAPTERS.items():
        if title == name or fn == name:
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
    alt_chapters = [f for f in CUSTOM_CHAPTERS if f not in chapters]
    if alt_chapters:
        alts = await validate_custom_report(
            db, chapters=alt_chapters,
            industry_l1=spec.industry_l1, province=spec.province,
            enterprise_ids=validation.get("enterprise_ids") or None,
        )
        for fn in alt_chapters:
            if alts["chapters"].get(fn, {}).get("available"):
                title = CUSTOM_CHAPTERS[fn][0]
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
        names = "、".join(CUSTOM_CHAPTERS[fn][0] for fn in empty if fn in CUSTOM_CHAPTERS)
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
            names = "、".join(CUSTOM_CHAPTERS[fn][0] for fn in empty if fn in CUSTOM_CHAPTERS)
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
            {"label": "直接生成固定报告（6 套模板）", "target": "/report?wizard=1"},
            {"label": "重新开始 AI 定制", "target": "/?custom=1"},
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
                            names = "、".join(CUSTOM_CHAPTERS[fn][0] for fn in skipped if fn in CUSTOM_CHAPTERS)
                            reply = (
                                f"已生成《{ctx.get('title')}》（编号 {report_id}）。"
                                f"注意：「{names}」在当前范围暂无数据已跳过，建议改用「全部样本」范围查看。"
                            )
                        else:
                            reply = f"已按你的方案生成《{ctx.get('title')}》，报告编号 {report_id}。可在报告中心查看、下载。"
                        followups = ["再定制一份", "换成固定报告"]
                        meta["actions"] = [
                            {"label": "查看并下载报告", "target": f"/report?highlight={report_id}"},
                            {"label": "再定制一份", "target": "/?custom=1"},
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
                        meta["actions"] = [{"label": "打开报告生成向导", "target": "/report?wizard=1"}]
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


async def route_chat(
    db: AsyncSession,
    query: str,
    session_id: str | None = None,
    enterprise_id: str | None = None,
    user: dict | None = None,
) -> dict:
    sid = await run_blocking(session_store.ensure_session_id, session_id)
    session_context = (await run_blocking(session_store.get_session, sid)) or {}
    if not enterprise_id:
        enterprise_id = session_context.get("enterprise_id")

    report_meta: dict | None = None
    intent_result: IntentResult | None = None
    sq: SemanticQuery | None = None

    if enterprise_id:
        branch = await _route_enterprise(db, query, enterprise_id, user=user)
        claims = branch["claims"]
        followups = branch["followups"]
        meta = branch["meta"]
        function = branch["function"]
        dimension = branch["dimension"]
        intent = branch["intent"]
        report_meta = branch["report_meta"]
        industry_l1 = branch["industry_l1"]
        province = branch["province"]
    else:
        intent_result = intent_engine.recognize(query, session_context=session_context)
        function = intent_result.function
        dimension = intent_result.dimension
        intent = intent_result.intent
        industry_l1 = intent_result.industry_l1
        province = intent_result.province

        # 定制报告：显式「定制」意图，或会话处于定制对话中 → AI 定制状态机（先于 FAQ/报告分支）
        custom_state = session_context.get("custom_report")
        if (custom_state and custom_state.get("active")) or function == "custom_report":
            return await _route_custom_report(db, query, sid, user=user, session_context=session_context)

        # FAQ/口径前置（规则层，先于「报告*」关键词）：产品说明/口径问句走 FAQ/方法论，
        # 避免「报告怎么生成」被 report 意图劫持成真报告生成。
        faq_sq = semantic_query.detect_faq_or_methodology(query)

        if faq_sq is None and function in ("report", "email_report"):
            # 报告意图走规则路径，直接调 run_judgment（保留覆盖度 claims + 严格审计测试）
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
                # 规则层已判定 FAQ/口径 → 直接采用，跳过 LLM 解析
                sq = faq_sq
            else:
                # LLM 优先：结构化解析 NL → SemanticQuery；失败降级规则转换
                if llm_reply.llm_available():
                    try:
                        parsed = await llm_semantic_parser.parse_semantic_query(
                            query,
                            session_context=session_context,
                            dictionary=metric_registry.build_llm_dictionary(),
                        )
                        if parsed is not None:
                            sq = semantic_query.correct_semantic_query(parsed, session_context)
                    except Exception as exc:
                        logger.debug("semantic parse failed: %s", exc)
                if sq is None:
                    # 对比前置：无 LLM（或 LLM 解析失败）时，识别「A 和 B 对比」产出 comparison，
                    # 否则再退回规则意图转换，避免把「江西和湖南对比」误判成普通切片。
                    sq = semantic_query.detect_rule_comparison(query) or semantic_query.intent_to_semantic_query(intent_result)

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
            try:
                claims, followups, meta = await judgment_service.run_semantic_query(db, sq, sid, intent=intent_result)
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
          meta["actions"] = [
              {"label": "直接生成固定报告（6 套模板）", "target": "/report?wizard=1"},
              {"label": "AI 定制报告（对话式自由组合）", "target": "/?custom=1"},
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
                if recipient and recipient.strip().lower() != user_email:
                    report_claims.append(
                        Claim(
                            claim="邮件仅可发送至当前登录账号邮箱，请使用报告中心的邮件功能。",
                            value=ClaimValue(metric="email_denied", number=None, unit=""),
                            trace=ClaimTrace(
                                table="auth",
                                field="email",
                                query_id="Q_email_report_denied",
                            ),
                            confidence="computed",
                            evidence_chain=["recipient_must_match_login"],
                        )
                    )
                elif recipient and email_service.is_configured():
                    try:
                        await run_blocking(
                            email_service.send_slice_report,
                            recipient,
                            ctx.get("title") or "风控报告",
                            Path(pdf_path),
                        )
                        report_claims.append(
                            Claim(
                                claim=f"报告已发送至 {recipient}。",
                                value=ClaimValue(metric="email_sent", number=None, unit=""),
                                trace=ClaimTrace(
                                    table="conclusion_store",
                                    field="claims",
                                    query_id="Q_email_report",
                                ),
                                confidence="computed",
                                evidence_chain=[f"recipient={recipient}"],
                            )
                        )
                        meta["email_sent"] = True
                    except Exception as exc:
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
                elif recipient and not email_service.is_configured():
                    report_claims.append(
                        Claim(
                            claim=(
                                f"报告已生成。邮件服务未配置（{email_service.NOT_CONFIGURED_MSG}），"
                                f"无法发送至 {recipient}，请从报告中心下载。"
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
            followups = ["下载后核对附录数据说明", "切换欺诈场景再出一份", "继续追问行业趋势"]
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

    reply, bundle, reply_source = await llm_reply.generate_claim_reply(
        query,
        claims,
        followups,
        report_hint=report_hint,
    )
    if not (reply or "").strip():
        reply = llm_reply._template_from_claims(claims, followups, with_prefix=False, report_hint=report_hint)
        reply_source = "template"

    charts = meta.get("charts")

    # synthesis 仅用于当轮展示，不写入 conclusion_store，避免多轮 headline 自污染
    persist_claims = without_synthesis_claims(claims)

    conclusion_id = await run_blocking(
        conclusion_store.save_conclusion,
        session_id=sid,
        function=function,
        dimension=dimension,
        claims=persist_claims,
        followups=list(bundle.followups or followups),
        evidence_hidden=True,
        meta={
            "intent": intent,
            "industry_l1": industry_l1,
            "province": province,
            "charts": charts,
            **{k: v for k, v in meta.items() if k != "charts"},
        },
    )

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
        "followups": list(bundle.followups or followups),
        "conclusion_id": conclusion_id,
        "evidence_hidden": True,
        "coverage": sorted(await run_blocking(conclusion_store.covered_functions, sid)),
        "report_hint": report_hint,
        "actions": (meta or {}).get("actions", []),
        "slice": {k: v for k, v in meta.items() if k != "charts"},
    }
    if report_meta:
        data["report"] = report_meta

    logger.info(
        "route_chat fn=%s dim=%s claims=%d reply[:120]=%r",
        function,
        dimension,
        len(claims),
        reply[:120],
    )

    return {
        "reply": reply,
        "reply_source": reply_source,
        # 双轨来源：数字/研判始终规则引擎；表述可为 LLM 润色；意图解析可为 LLM
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
    }


# --- 兼容旧测试 ---
def _radar_chart(ent: dict) -> dict:
    from app.services.chart_payloads import enterprise_radar_chart

    return enterprise_radar_chart(ent)


def _bar_chart(items: list[dict], metric: str = "overall_score", title: str = "综合分") -> dict:
    return {
        "type": "bar",
        "data": {
            "labels": [i.get("enterprise_name") or i.get("display_label") or i.get("industry_l1", "") for i in items],
            "series": [{"name": title, "values": [i.get(metric, 0) for i in items]}],
        },
    }


def _missing_enterprise_message(intent: str) -> str:
    return "匿名切片模式请按行业/地区提问，例如：分析各行业的趋势走向"


def _unknown_enterprise_message() -> str:
    return "匿名切片模式不支持具名企业查询，请改问行业趋势、真实性或舞弊信号。"
