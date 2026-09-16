"""对话行为分类：DialogAct 为一等真源（LLM instructor + pydantic 封闭枚举）。

铁律：
- LLM 只出 act + 槽位，不出库存数字/名单；
- 有 LLM 时禁止正则白名单门禁；无 LLM 时仅软提示 + 低置信反问；
- resolve_scope 门禁只应对 analyze/drill，由路由层保证。
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services import llm_reply

logger = logging.getLogger(__name__)

ActName = Literal[
    "negotiate_scope",
    "bind_subject",
    "analyze",
    "drill",
    "product_faq",
    "meta_session",
    "custom_report",
]
ScenarioName = Literal["loan", "rating", "warn", "audit"]
ScopeTarget = Literal["individual", "cohort"]
AskKind = Literal["overview", "list", "count", "entry_help"]

CONFIDENCE_CLARIFY = 0.55

RefusalKind = Literal["fabrication", "out_of_domain"]

FABRICATION_REFUSE_MSG = (
    "数字只来自系统数据，无法编造或伪造。请问想查询哪方面的真实数据？"
)

# 无 LLM 软降级兜底用的关键词（非主路径；主路径由 schema refusal_kind 判定）
_SOFT_FABRICATE_KW = (
    "编造", "编一个", "帮我编", "伪造", "假造", "捏造", "虚构", "造假数据", "造一个", "编一份",
)
_SOFT_OOD_KW = (
    "天气", "午饭", "晚饭", "吃什么", "电影", "电视剧", "足球", "篮球",
    "游戏", "讲个笑话", "星座", "算命", "股票行情",
)

# 聚合语义：未绑定主体时 analyze 默认 cohort（契约，非词表白名单堆砌）
_AGGREGATE_ANALYZE_RE = re.compile(
    r"(各行业|行业趋势|趋势走向|走向|走势|同比|分布|信号最多|群体|"
    r"全库|全样本|整体风险|哪里信号|风险在哪|预警主体|行业对比|"
    r"真实性交叉|按地区|地区拆分|拆分趋势)"
)
_INDIVIDUAL_DEIXIS_RE = re.compile(
    r"(这家|该企业|这个企业|该户|本企业|企业\s*\d+|能贷|放贷|贷不贷|"
    r"信用怎么样|给不给授信|换一家)"
)
_GREETING_RE = re.compile(
    r"^(早上好|上午好|中午好|下午好|晚上好|你好|您好|嗨|哈喽|hello|hi|"
    r"早|早安|多谢|谢谢|感谢|辛苦了)[！!。.~～\s]*$",
    re.I,
)
_MULTI_INTENT_SEP_RE = re.compile(r"[；;]|\n")


def looks_aggregate_analyze(query: str) -> bool:
    q = (query or "").strip()
    if not q:
        return False
    if _INDIVIDUAL_DEIXIS_RE.search(q) and not _AGGREGATE_ANALYZE_RE.search(q):
        return False
    return bool(_AGGREGATE_ANALYZE_RE.search(q))


def looks_greeting(query: str) -> bool:
    return bool(_GREETING_RE.match((query or "").strip()))


def split_multi_intent(query: str) -> list[str]:
    """多意图拼句拆分；单意图返回空列表。"""
    q = (query or "").strip()
    if not q or not _MULTI_INTENT_SEP_RE.search(q):
        return []
    parts = [p.strip() for p in re.split(r"[；;]", q) if p.strip()]
    # 过滤「可继续追问：」前缀残留
    cleaned = []
    for p in parts:
        p = re.sub(r"^可继续追问[:：]\s*", "", p).strip()
        if p:
            cleaned.append(p)
    return cleaned if len(cleaned) >= 2 else []



class DialogAct(BaseModel):
    act: ActName
    scenario: ScenarioName | None = None
    subject_ref: str | None = None
    scope_target: ScopeTarget | None = None
    drill_op: str | None = None
    ask_kind: AskKind | None = None
    industry_l1: str | None = None
    province: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    # M1 弃权三态：can_answer=False → clarify（有 clarify_question）或 abstain（无）
    can_answer: bool = Field(default=True, description="False 时走 clarify 或 abstain 路径")
    clarify_question: str | None = Field(default=None, description="反问内容（一句话），can_answer=False 时使用")
    # 强制弃权类别：由 LLM/软降级填入，路由层统一落地文案（禁止正则主路径）
    refusal_kind: RefusalKind | None = Field(
        default=None,
        description="fabrication=拒绝编造；out_of_domain=超纲弃权；null=非弃权",
    )
    # M1 工具调用计划：LLM 从能力地图选出的工具列表
    tools: list[dict] = Field(default_factory=list, description="LLM 选出的工具调用计划（MetricTool 列表）")


def apply_refusal_policy(act: DialogAct) -> DialogAct:
    """将 refusal_kind 落到 can_answer / clarify_question（单一真源）。"""
    if act.refusal_kind == "fabrication":
        return act.model_copy(
            update={
                "can_answer": False,
                "clarify_question": FABRICATION_REFUSE_MSG,
                "confidence": max(float(act.confidence or 0), 0.95),
            }
        )
    if act.refusal_kind == "out_of_domain":
        return act.model_copy(
            update={
                "can_answer": False,
                "clarify_question": None,
                "confidence": max(float(act.confidence or 0), 0.95),
            }
        )
    return act


def _soft_refusal_kind(query: str) -> RefusalKind | None:
    """无 LLM 时的弃权兜底（关键词，非正则主路径）。"""
    q = (query or "").strip()
    if not q:
        return None
    if any(k in q for k in _SOFT_FABRICATE_KW):
        return "fabrication"
    if any(k in q for k in _SOFT_OOD_KW):
        return "out_of_domain"
    return None


def merge_inventory_focus(act: DialogAct, state: dict[str, Any] | None) -> DialogAct:
    """继承会话库存焦点：追问「那些/再列/呢」时补 filters，不靠关键词补丁门禁。"""
    focus = ((state or {}).get("inventory_focus") or {}) if state else {}
    data = act.model_dump()
    if not data.get("industry_l1") and focus.get("industry_l1"):
        data["industry_l1"] = focus["industry_l1"]
    if not data.get("province") and focus.get("province"):
        data["province"] = focus["province"]
    # 有行业过滤器但未声明 ask_kind → 默认 list（问切片通常要名单）
    if data.get("act") == "negotiate_scope":
        if data.get("industry_l1") or data.get("province"):
            if not data.get("ask_kind"):
                data["ask_kind"] = "list"
        elif not data.get("ask_kind"):
            data["ask_kind"] = "overview"
    try:
        return DialogAct.model_validate(data)
    except Exception:
        return act


def focus_from_act(act: DialogAct) -> dict[str, Any] | None:
    if act.act != "negotiate_scope":
        return None
    if not (act.industry_l1 or act.province):
        return None
    return {
        "industry_l1": act.industry_l1,
        "province": act.province,
        "ask_kind": act.ask_kind or "list",
    }


def from_followup(followup: dict[str, Any] | None) -> DialogAct | None:
    """chip / 结构化 followup → DialogAct（与自然语言走同一 dispatch）。"""
    if not followup or not isinstance(followup, dict):
        return None
    t = followup.get("type")
    params = followup.get("params") if isinstance(followup.get("params"), dict) else {}

    if t == "dialog_act":
        raw = {**params}
        if followup.get("act"):
            raw["act"] = followup["act"]
        try:
            return DialogAct.model_validate({**raw, "confidence": float(raw.get("confidence") or 1.0)})
        except Exception:
            return None

    if t == "switch_scope":
        target = str(followup.get("target") or params.get("target") or "").strip()
        if params.get("open_picker"):
            return DialogAct(act="negotiate_scope", ask_kind="entry_help", confidence=1.0)
        if target == "cohort":
            return DialogAct(
                act="negotiate_scope",
                ask_kind="overview",
                scope_target="cohort",
                confidence=1.0,
            )
        if target == "individual" or params.get("use_demo") or params.get("enterprise_id"):
            ref = None
            if params.get("use_demo"):
                ref = "演示"
            elif params.get("enterprise_id"):
                ref = str(params.get("display_name") or params["enterprise_id"])
            return DialogAct(
                act="bind_subject",
                subject_ref=ref,
                scope_target="individual",
                confidence=1.0,
            )

    if t == "drilldown":
        return DialogAct(
            act="drill",
            drill_op=str(followup.get("op") or "") or None,
            scope_target="cohort",
            confidence=1.0,
        )

    if t == "bootstrap":
        return DialogAct(act="meta_session", confidence=1.0)

    return None


async def classify(query: str | None, state: dict[str, Any] | None = None) -> DialogAct:
    """主路径：LLM 结构化分类（含 refusal_kind）；不可用或失败 → 软降级。"""
    q = (query or "").strip()
    state = state or {}
    if not q:
        return DialogAct(act="meta_session", confidence=0.9)

    # 定制报告活跃会话：优先保持 custom_report，避免被协商/分析抢走
    cr = state.get("custom_report") if isinstance(state.get("custom_report"), dict) else None
    if cr and cr.get("active"):
        return DialogAct(act="custom_report", confidence=1.0)

    if llm_reply.llm_available():
        act = await _llm_classify(q, state)
        if act is not None:
            # 红线 §2.3：LLM 主路径禁止正则 _normalize_act；只合并会话焦点 + 弃权策略
            act = apply_refusal_policy(merge_inventory_focus(act, state))
            if (
                act.refusal_kind is None
                and act.confidence < CONFIDENCE_CLARIFY
                and act.can_answer
            ):
                act = act.model_copy(
                    update={
                        "can_answer": False,
                        "clarify_question": act.clarify_question
                        or "您能说得更具体一些吗？比如想看哪个行业或哪家企业？",
                    }
                )
            return act
        logger.info("dialog_act llm classify failed, soft fallback q=%r", q[:40])

    # 无 LLM / LLM 失败：软降级才允许 _normalize_act（关键词兜底）
    act = apply_refusal_policy(
        merge_inventory_focus(_normalize_act(_soft_fallback(q, state), q, state), state)
    )
    if act.refusal_kind is None and act.confidence < CONFIDENCE_CLARIFY and act.can_answer:
        act = act.model_copy(
            update={
                "can_answer": False,
                "clarify_question": act.clarify_question
                or "您能说得更具体一些吗？比如想看哪个行业或哪家企业？",
            }
        )
    return act


def _normalize_act(act: DialogAct, query: str, state: dict[str, Any]) -> DialogAct:
    """轻量校正：list≠drill；未绑个体分析默认 individual 门禁；补行业槽。"""
    from app.services.intent_engine import _match_industry, _match_province

    data = act.model_dump()
    q = query or ""

    if not data.get("industry_l1"):
        data["industry_l1"] = _match_industry(q)
    if not data.get("province"):
        data["province"] = _match_province(q)

    # 列名单 / 有哪些家 → 永不 drill
    if data.get("act") == "drill" and re.search(
        r"哪些|那些|名单|有哪|列一下|是谁|几家|多少家|展开", q
    ):
        data["act"] = "negotiate_scope"
        data["ask_kind"] = data.get("ask_kind") or "list"
        data["drill_op"] = None

    if data.get("act") == "negotiate_scope":
        if data.get("industry_l1") or data.get("province"):
            if not data.get("ask_kind") or data.get("ask_kind") == "overview":
                if re.search(r"多少家|有多少|几家", q) and not re.search(r"哪些|那些|名单|是谁", q):
                    data["ask_kind"] = "count"
                else:
                    data["ask_kind"] = "list"
        elif re.search(r"能分析哪些|可以分析哪些|能分析什么|有哪些行业|能做什么", q):
            data["ask_kind"] = "overview"
        elif not data.get("ask_kind"):
            data["ask_kind"] = "entry_help" if re.search(r"怎么选|如何选", q) else "overview"
        # LLM 误把「能分析哪些」标成 list
        if data.get("ask_kind") == "list" and not (data.get("industry_l1") or data.get("province")):
            if re.search(r"能分析哪些|可以分析哪些|有哪些行业|能做什么", q):
                data["ask_kind"] = "overview"

    # analyze 未声明 scope_target：聚合问法默认 cohort；指代单户才 individual
    if data.get("act") == "analyze" and not data.get("scope_target"):
        cur = (state or {}).get("scope") or "unbound"
        if cur == "cohort":
            data["scope_target"] = "cohort"
        elif cur == "individual":
            data["scope_target"] = "individual"
        else:
            # unbound：聚合/趋势/分布 → cohort；否则才个体门禁
            if looks_aggregate_analyze(q):
                data["scope_target"] = "cohort"
            else:
                data["scope_target"] = "individual"

    # 「刚才那些家还有吗」是库存指代，不是 meta
    if data.get("act") == "meta_session" and re.search(
        r"刚才那些|那些家|还有吗|还在吗|那些还", q
    ):
        data["act"] = "negotiate_scope"
        data["ask_kind"] = "list" if ((state or {}).get("inventory_focus") or {}).get("industry_l1") else "overview"

    # 「该查谁优先」等是分析，不是协商/入口
    if data.get("act") in ("negotiate_scope", "meta_session", "product_faq") and re.search(
        r"该查谁|要查谁|优先核查|哪里可疑要查|哪里不对劲", q
    ):
        data["act"] = "analyze"
        data["scenario"] = "audit" if re.search(r"查|可疑|稽查", q) else "warn"
        cur = (state or {}).get("scope") or "unbound"
        data["scope_target"] = "cohort" if cur == "cohort" else "individual"

    # 未说「定制」的生成报告 ≠ custom_report（留给个体/切片报告意图）
    if data.get("act") == "custom_report" and not re.search(
        r"定制|自定义|AI定制", q
    ):
        data["act"] = "analyze"
        cur = (state or {}).get("scope") or "unbound"
        data["scope_target"] = "individual" if cur == "individual" else (
            "cohort" if cur == "cohort" else "individual"
        )

    # 「那X呢」且非风险词 → 协商切片，不要 bind
    if data.get("act") == "bind_subject" and re.search(r"呢", q) and not re.search(
        r"能贷|信用|可疑|不对劲|换一家|企业\d+", q
    ):
        ind = data.get("industry_l1") or _match_industry(q)
        if ind:
            data["act"] = "negotiate_scope"
            data["ask_kind"] = "list"
            data["industry_l1"] = ind
            data["subject_ref"] = None

    # unbound：仅当明确指代单户却标成 cohort 时拉回 individual（禁止反向把聚合打成个体）
    if (
        data.get("act") == "analyze"
        and ((state or {}).get("scope") or "unbound") == "unbound"
        and data.get("scope_target") == "cohort"
        and _INDIVIDUAL_DEIXIS_RE.search(q)
        and not looks_aggregate_analyze(q)
    ):
        data["scope_target"] = "individual"

    # 误把「继续分析」标成 drill：仅允许舞弊三下钻 op；其余改 analyze
    if data.get("act") == "drill":
        from app.services.followup_items import DRILLDOWN_OPS

        op = (data.get("drill_op") or "").strip()
        if op and op not in DRILLDOWN_OPS:
            data["act"] = "analyze"
            data["drill_op"] = None
            data["scope_target"] = data.get("scope_target") or "cohort"
        elif not op and looks_aggregate_analyze(q):
            data["act"] = "analyze"
            data["drill_op"] = None
            data["scope_target"] = "cohort"

    try:
        return DialogAct.model_validate(data)
    except Exception:
        return act


async def _llm_classify(query: str, state: dict[str, Any]) -> DialogAct | None:
    system = _build_system(state)
    user = f"用户话：{query}"
    model, llm_params = llm_reply._llm_completion_params()
    try:
        import instructor
        from openai import OpenAI

        api_key = llm_params.get("api_key") or ""
        base = llm_params.get("api_base") or "https://api.deepseek.com"
        raw_model = (os.getenv("LLM_MODEL") or "deepseek-v4-pro").strip()
        if raw_model.startswith("openai/"):
            raw_model = raw_model[len("openai/") :]

        client = instructor.from_openai(OpenAI(api_key=api_key, base_url=base))
        kwargs: dict = {
            "model": raw_model,
            "response_model": DialogAct,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_retries": 2,
            "temperature": 0.0,
        }
        extra = llm_reply._llm_extra_body(raw_model)
        if extra:
            kwargs["extra_body"] = extra
        return client.chat.completions.create(**kwargs)
    except Exception as e1:
        logger.info("instructor dialog_act failed (%s), try litellm json", e1)

    try:
        import litellm

        completion_kwargs: dict = {
            "model": model,
            **llm_params,
            "messages": [
                {"role": "system", "content": system + " 只输出一个 JSON 对象。"},
                {"role": "user", "content": user},
            ],
            "max_tokens": 350,
            "temperature": 0.0,
            "timeout": 45,
            "response_format": {"type": "json_object"},
        }
        extra = llm_reply._llm_extra_body(model)
        if extra:
            completion_kwargs["extra_body"] = extra
        response = litellm.completion(**completion_kwargs)
        raw = llm_reply._extract_llm_content(response)
        return DialogAct.model_validate_json(raw)
    except Exception as e2:
        logger.warning("litellm dialog_act fallback failed: %s", e2)
        return None


def _build_system(state: dict[str, Any]) -> str:
    from app.services.intent_engine import industry_l1_options, province_options
    from app.services.metric_registry import to_tool_schema
    from app.services.persona import build_persona_prompt

    scope = (state or {}).get("scope") or "unbound"
    subject = (state or {}).get("subject") or {}
    name = subject.get("display_name") or "无"
    focus = (state or {}).get("inventory_focus") or {}
    inds = "、".join(industry_l1_options()[:12])
    provs = "、".join(province_options()[:12])
    persona = build_persona_prompt((state or {}).get("scenario"))
    chapters = chapter_tool_catalog()
    chap_desc = "|".join(f"{c['chapter']}({c['title']})" for c in chapters)
    # 能力地图：章节工具为主；指标工具名作补充白名单（动态自 registry）
    metric_names = "、".join(t["name"] for t in to_tool_schema()[:16])
    return (
        persona + "\n"
        "你是对话行为分类器。只输出 DialogAct JSON，不要解释、不要编造数字或企业名单。\n"
        "act：negotiate_scope|bind_subject|analyze|drill|product_faq|meta_session|custom_report。\n"
        "- negotiate_scope：库存/名单/计数/怎么选。ask_kind=overview|list|count|entry_help。"
        "问某行业有哪些/是谁/名单→list并填 industry_l1；问多少家→count；问能分析哪些/有哪些行业→overview；"
        "问怎么选→entry_help。列名单绝不是 drill。\n"
        "- bind_subject：选定/换一家主体（随便一家、企业3、换一家）。"
        "「那建筑呢」若在问行业名单则是 negotiate_scope+list，不是 bind。\n"
        "- analyze：风险研判。各行业/趋势/走向/分布/真实性交叉/按地区→scope_target=cohort；"
        "这家/能贷/信用怎么样等指代单户→individual。未选主体的聚合问法默认 cohort。\n"
        "- drill：仅舞弊结论后的三下钻（按行业拆/Top名单/漏斗）。"
        "「进一步看真实性」「按地区拆分趋势」是 analyze 不是 drill。\n"
        "- product_faq：仅导入/指标口径/报告怎么生成。\n"
        "- meta_session：问候寒暄、当前在看谁、帮我综合、会话状态。\n"
        "- custom_report：我要定制报告/自定义报告/AI定制。\n"
        f"industry_l1 只能从 [{inds}] 选或 null；province 从 [{provs}] 选或 null。\n"
        "scenario 仅 analyze：loan|rating|warn|audit。\n"
        "confidence：乱码/答非所问 <0.55。\n"
        "refusal_kind：用户要求编造/伪造数字或名单 → fabrication；"
        "完全超出财税风控（天气/闲聊/娱乐等）→ out_of_domain；其余 null。\n"
        "can_answer：refusal_kind 非 null 时必须 false；意图不清/缺槽位时也 false。\n"
        "clarify_question：fabrication 时填一句拒绝说明；out_of_domain 必须 null；"
        "仅意图不清时填反问。\n"
        f"tools：act=analyze 时从章节工具选 1..N：{chap_desc}。"
        "每项填 {chapter, dimension, filters}；filters 可含 industry_l1/province。"
        f"也可填指标工具名（如 {metric_names}）映射到对应章节。非 analyze 时 tools=[]。\n"
        f"当前 scope={scope} 主体={name} inventory_focus={focus or '无'}。"
    )


def _soft_fallback(query: str, state: dict[str, Any]) -> DialogAct:
    """无 LLM：软提示填槽；不确定则低置信。编造/超纲仅作兜底关键词。"""
    from app.services.intent_engine import _match_industry, _match_province

    q = query.strip()
    soft_refuse = _soft_refusal_kind(q)
    if soft_refuse:
        return DialogAct(
            act="meta_session",
            confidence=1.0,
            can_answer=False,
            refusal_kind=soft_refuse,
            clarify_question=FABRICATION_REFUSE_MSG if soft_refuse == "fabrication" else None,
        )

    ind = _match_industry(q)
    prov = _match_province(q)

    if re.search(r"定制报告|自定义报告|AI定制|帮我定制|我要定制|报告定制|定制一下", q):
        return DialogAct(act="custom_report", confidence=0.85)

    if re.search(r"(怎么|如何).*(导入|上传).*(数据)?|(数据).*(怎么|如何).*(导入|上传)", q):
        return DialogAct(act="product_faq", confidence=0.75)
    if re.search(r"(指标|口径|评分|权重|算法).*(怎么|如何).*(算|定义)|怎么算", q):
        return DialogAct(act="product_faq", confidence=0.75)
    if re.search(r"(报告).*(怎么|如何).*(生成|导出|下载)", q) and "定制" not in q:
        return DialogAct(act="product_faq", confidence=0.7)

    if looks_greeting(q):
        return DialogAct(act="meta_session", confidence=0.9)

    if re.search(r"帮我综合|综合一下|汇总这几轮|当前在看|现在看的是谁|会话状态|聊到哪", q):
        return DialogAct(act="meta_session", confidence=0.8)

    # 继续分析（契约：走 analyze，永不假 drill）
    if re.search(r"真实性交叉|经营真实性|进一步看真实", q):
        return DialogAct(act="analyze", scenario="warn", scope_target="cohort", confidence=0.8)
    if re.search(r"按地区.*趋势|地区拆分|按地区拆", q):
        return DialogAct(act="analyze", scenario="rating", scope_target="cohort", confidence=0.8)
    if re.search(r"各行业.*趋势|趋势走向|行业趋势|分析各行业", q):
        return DialogAct(act="analyze", scenario="warn", scope_target="cohort", confidence=0.85)
    if re.search(r"调.*票据|票据.*凭证|货物凭证", q):
        # 路由层会走 action；此处标 analyze 会被 followup action 抢先；无 followup 时当 cohort 稽查提示
        return DialogAct(act="analyze", scenario="audit", scope_target="cohort", confidence=0.7)

    if re.search(r"随便(来|选|看)?一家|任意一家|换一家|换个企业|试用演示", q):
        return DialogAct(act="bind_subject", subject_ref=q, scope_target="individual", confidence=0.7)
    m_ent = re.search(r"企业\s*(\d+)|ENT\s*(\d+)", q, re.I)
    if m_ent and not re.search(r"哪些|那些|名单|有哪", q):
        return DialogAct(
            act="bind_subject",
            subject_ref=m_ent.group(0),
            scope_target="individual",
            confidence=0.75,
        )

    # 真正下钻：仅舞弊三下钻措辞（且非名单/继续分析）
    if re.search(r"按行业拆|拆开看异常|行业集中度|风险筛查漏斗|漏斗|Top\s*名单|top名单", q) and not re.search(
        r"哪些企业|那些家|名单是谁|有哪些|真实性|按地区.*趋势|趋势走向", q
    ):
        op = "show_funnel" if re.search(r"漏斗", q) else (
            "top_list" if re.search(r"Top|top名单|名单", q) else "group_by_industry"
        )
        return DialogAct(
            act="drill",
            drill_op=op,
            scope_target="cohort",
            confidence=0.7,
        )

    if re.search(r"能贷|放贷|贷不贷", q):
        return DialogAct(act="analyze", scenario="loan", scope_target="individual", confidence=0.7)
    if re.search(r"信用怎么样|评级|信用等级", q):
        return DialogAct(act="analyze", scenario="rating", scope_target="individual", confidence=0.7)
    if re.search(r"不对劲|预警|哪里不对", q):
        st: ScopeTarget = "cohort" if (state or {}).get("scope") == "cohort" else "individual"
        return DialogAct(act="analyze", scenario="warn", scope_target=st, confidence=0.7)
    if re.search(r"可疑|该查|稽查|优先核查|要查谁", q):
        st: ScopeTarget = "cohort" if (state or {}).get("scope") == "cohort" else "individual"
        if (state or {}).get("scope") == "unbound":
            # 聚合/无指代 → cohort；明确「这家」才个体
            st = "individual" if _INDIVIDUAL_DEIXIS_RE.search(q) and not looks_aggregate_analyze(q) else "cohort"
        return DialogAct(act="analyze", scenario="audit", scope_target=st, confidence=0.7)
    if looks_aggregate_analyze(q) or re.search(r"全库|全样本|哪里信号最多|整体风险", q):
        return DialogAct(act="analyze", scenario="warn", scope_target="cohort", confidence=0.75)

    # 库存协商（含行业切片）
    listish = bool(re.search(r"哪些|那些|名单|是谁|列一下|有哪|展开|再列", q))
    countish = bool(re.search(r"多少家|有多少|几家", q))
    entryish = bool(re.search(r"怎么选|如何选", q))
    overviewish = bool(
        re.search(
            r"能分析哪些|可以分析|能做什么|有哪些行业|库存|样本|刚才那些|怎么选",
            q,
        )
    )
    if ind or prov or listish or countish or entryish or overviewish:
        ask: AskKind = "overview"
        # 「能分析哪些企业」是总览，不是 list
        if re.search(r"能分析哪些|可以分析哪些|能分析什么|可以分析什么|有哪些行业|系统能做什么|能做什么", q):
            ask = "overview"
        elif entryish and not (ind or listish or countish):
            ask = "entry_help"
        elif countish and not listish:
            ask = "count"
        elif ind or prov:
            ask = "count" if (countish and not listish) else "list"
        elif listish and re.search(r"名单|是谁|列一下|那些家|有哪些企业", q):
            # 无行业的「有哪些企业」仍总览；带名单/是谁更像要列全库示例
            if re.search(r"有哪些企业|哪些企业", q) and not re.search(r"名单|是谁|列一下", q):
                ask = "overview"
            else:
                ask = "list"
        if re.search(r"呢", q) and ind:
            ask = "list"
        return DialogAct(
            act="negotiate_scope",
            ask_kind=ask,
            industry_l1=ind,
            province=prov,
            confidence=0.7 if (ind or overviewish or listish) else 0.6,
        )

    return DialogAct(act="negotiate_scope", ask_kind="overview", confidence=0.35)


def needs_clarify(act: DialogAct) -> bool:
    return float(act.confidence or 0) < CONFIDENCE_CLARIFY


def needs_abstain(act: DialogAct) -> bool:
    """M1：是否需要弃权（can_answer=False 且无 clarify_question）。"""
    return not act.can_answer and not act.clarify_question


def get_clarify_question(act: DialogAct) -> str | None:
    """M1：获取反问内容。can_answer=False 且有 clarify_question 时返回。"""
    if not act.can_answer and act.clarify_question:
        return act.clarify_question
    return None


def _resolve_one_tool(first: dict[str, Any]) -> dict[str, Any]:
    """解析单个 tool dict → {function, dimension, industry_l1?, province?}；不合法返回 {}。"""
    from app.services.report_templates import CHAPTER_REGISTRY

    if not isinstance(first, dict):
        return {}
    raw = (
        first.get("chapter")
        or first.get("name")
        or first.get("tool")
        or ""
    )
    raw = str(raw).strip()
    if raw.startswith("chapter_"):
        raw = raw[len("chapter_"):]
    if raw.startswith("metric_"):
        # 指标工具：按 KPI 反查章节
        metric_key = raw[len("metric_"):]
        for chap, entry in CHAPTER_REGISTRY.items():
            for kpi in entry.get("kpis") or []:
                if kpi.get("metric") == metric_key:
                    raw = chap
                    break
            else:
                continue
            break
    if raw not in CHAPTER_REGISTRY:
        return {}
    entry = CHAPTER_REGISTRY[raw]
    dim = first.get("dimension") or entry.get("default_dimension") or "overall"
    if dim not in ("overall", "industry", "region", "time", "signal"):
        dim = entry.get("default_dimension") or "overall"
    out: dict[str, Any] = {"function": raw, "dimension": dim}
    filters = first.get("filters") if isinstance(first.get("filters"), dict) else {}
    ind = filters.get("industry_l1") or first.get("industry_l1")
    prov = filters.get("province") or first.get("province")
    if ind:
        out["industry_l1"] = str(ind)
    if prov:
        out["province"] = str(prov)
    return out


def resolve_analyze_tools(act: DialogAct) -> dict[str, Any]:
    """从 act.tools 解析第一个工具的章节/过滤槽位（兼容旧单意图路径）。

    多意图请用 resolve_all_analyze_tools 拿全部工具计划。
    """
    tools = act.tools or []
    if not tools or not isinstance(tools[0], dict):
        return {}
    return _resolve_one_tool(tools[0])


def resolve_all_analyze_tools(act: DialogAct) -> list[dict[str, Any]]:
    """红线 §2.2 多意图并行：解析 act.tools 中所有合法工具计划。

    返回 [{function, dimension, industry_l1?, province?}, ...]；
    空工具 / 全不合法 → 空列表（路由层走单意图 intent_engine 兜底）。
    """
    out: list[dict[str, Any]] = []
    for t in act.tools or []:
        resolved = _resolve_one_tool(t)
        if resolved:
            out.append(resolved)
    return out


def chapter_tool_catalog() -> list[dict[str, Any]]:
    """章节工具表（能力地图之一），供 prompt / 路由共用。"""
    from app.services.report_templates import CHAPTER_REGISTRY

    return [
        {
            "chapter": key,
            "name": f"chapter_{key}",
            "title": entry.get("title"),
            "description": entry.get("desc"),
            "default_dimension": entry.get("default_dimension") or "overall",
            "data_shapes": list(entry.get("data_shapes") or []),
        }
        for key, entry in CHAPTER_REGISTRY.items()
    ]


def multi_intent_clarify(parts: list[str]) -> dict[str, Any]:
    """多意图拼句：请用户点选，每项结构化 dialog_act/navigate/action。"""
    from app.services import followup_items as fu

    items: list[dict[str, Any]] = []
    for label in parts[:5]:
        items.extend(fu.normalize_legacy_strings([label])[:1])
    if not items:
        items = fu.build_default_followups()
    return {
        "reply": "这句话里有好几件事。请先选一项，我按这一项继续：",
        "followup_items": items[:6],
        "dialog_act": {"act": "meta_session", "confidence": 1.0, "multi_intent": True},
    }


def clarify_payload(act: DialogAct | None = None) -> dict[str, Any]:
    from app.services import followup_items as fu
    from app.services import scope_state as ss

    reply = (
        "我没太确定你的意思。你是想先看能分析哪些企业，"
        "还是已经选好范围、要看风险结论？"
        "也可以直接点下面入口。"
    )
    items = [
        fu.item(
            type="dialog_act",
            label="先看能分析哪些",
            params={"act": "negotiate_scope", "ask_kind": "overview", "confidence": 1.0},
        ),
        *ss.unbound_entry_items()[:2],
        fu.item(
            type="dialog_act",
            label="全库哪里信号多",
            params={
                "act": "analyze",
                "scenario": "warn",
                "scope_target": "cohort",
                "confidence": 1.0,
            },
        ),
    ]
    return {"reply": reply, "followup_items": items, "dialog_act": (act.model_dump() if act else None)}
