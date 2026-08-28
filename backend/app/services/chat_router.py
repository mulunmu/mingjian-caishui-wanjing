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
from app.services.intent_engine import IntentResult
from app.services.judgment_service import without_synthesis_claims
from app.services.report_templates import PremiumReportLocked, resolve_scenario
from app.services.sync_runner import run_blocking

logger = logging.getLogger(__name__)


async def _route_enterprise(
    db: AsyncSession, query: str, enterprise_id: str
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
        try:
            from app.services.slice_report import generate_enterprise_report

            report_id, _pdf_path, ctx = await generate_enterprise_report(db, enterprise_id)
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


async def route_chat(
    db: AsyncSession,
    query: str,
    session_id: str | None = None,
    enterprise_id: str | None = None,
) -> dict:
    sid = await run_blocking(session_store.ensure_session_id, session_id)
    session_context = (await run_blocking(session_store.get_session, sid)) or {}
    if not enterprise_id:
        enterprise_id = session_context.get("enterprise_id")

    report_meta: dict | None = None
    intent_result: IntentResult | None = None
    sq: SemanticQuery | None = None

    if enterprise_id:
        branch = await _route_enterprise(db, query, enterprise_id)
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

    # 报告意图（切片）：直接产出切片 PDF（保留覆盖度 claims）
    if function in ("report", "email_report"):
        coverage_claims = list(claims)
        try:
            from app.services.slice_report import generate_slice_report

            scenario_key = resolve_scenario(query=query)
            report_id, pdf_path, ctx = await generate_slice_report(
                db,
                scenario=scenario_key,
                session_id=sid,
                query=query,
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
                recipient = intent_result.recipient
                if recipient and email_service.is_configured():
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
