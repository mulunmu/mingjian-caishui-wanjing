"""
LLM 回复：只组织语言，不产生新数字。

优先用 instructor 结构化 ClaimBundle；失败则模板拼接 computed claims。
"""
from __future__ import annotations

import json
import logging
import os
import re

from dotenv import load_dotenv

from pydantic import BaseModel, Field

from app.schemas.claim import Claim, ClaimBundle, filter_claims
from app.services.hallucination_guard import (
    claims_have_risk_verdict,
    collect_allowed_numbers,
    filter_unanchored_sentences,
    sentence_has_anchor,
    sentence_has_risk_direction,
)
from app.services.report_templates import BANNED_AI_PHRASES

load_dotenv()

logger = logging.getLogger(__name__)


class NarrationPlan(BaseModel):
    """A.4 章节解读 document plan：只允许改写句列表（禁止自由散文）。

    红线 §2.1：不限制句数句式，只约束数字来源。max_length 上限仅作为
    API 边界防护（防御异常 LLM 输出爆炸），不再作为对 LLM 表达的硬约束。
    """

    sentences: list[str] = Field(default_factory=list, max_length=32)


class SummaryPlan(BaseModel):
    """A.4 执行摘要 document plan：只允许改写句列表。

    同 NarrationPlan：不限制句数，只约束数字与事实来源。
    """

    sentences: list[str] = Field(default_factory=list, max_length=32)

TEMPLATE_PREFIX = ""  # M3：去掉「[规则模板生成]」前缀；保留常量名兼容旧引用
FALLBACK_REPLY = "分析完成。整体判断请结合关键数字；可继续追问放贷、评级、预警或稽查场景。"

# 兼容旧测试/调用
WARNING_LABELS = {
    "tax_on_time_rate_low": "纳税准时率低",
    "invoice_monthly_avg_drop": "发票月均大幅下降",
    "credit_level_risk": "信用等级风险",
    "social_trend_shrink": "社保趋势缩减",
    "revenue_deviation_high": "营收偏差过高",
    "legal_compliance_risk": "法律合规风险",
    "legal_enforcement_risk": "失信/被执行",
}


def _is_llm_configured() -> bool:
    key = os.getenv("LLM_API_KEY", "")
    return bool(key and key != "your-api-key-here")


def is_llm_configured() -> bool:
    return _is_llm_configured()


def llm_available() -> bool:
    """LLM 当前是否可用：已配置 key 且未耗尽每日配额。

    配额耗尽时返回 False，使整条链路（解析/润色/报告解读）降级为规则/模板，
    而不是在 chat 层硬抛 429。is_llm_configured() 仍只表达「是否配置了 key」，
    供 health / 前端展示用。
    """
    if not _is_llm_configured():
        return False
    from app.services import rate_limiter

    return rate_limiter.check_llm_limit()


def _ensure_reply(text: str) -> str:
    cleaned = (text or "").strip()
    return cleaned if cleaned else FALLBACK_REPLY


def _sanitize_conclusions(conclusions: list[str], claims: list[Claim]) -> list[str]:
    """丢弃引入未授权数字的句子（与 hallucination_guard 同口径）。"""
    kept, dropped = filter_unanchored_sentences(conclusions, claims)
    for line in dropped:
        logger.info("drop hallucinated conclusion: %r", line[:80])
    return [s.strip() for s in kept if s.strip()]


def _template_from_claims(
    claims: list[Claim],
    followups: list[str],
    with_prefix: bool = False,
    report_hint: str | None = None,
    query: str | None = None,
) -> str:
    from app.services.plain_language import build_advisor_reply, translate_terms

    # with_prefix 保留参数兼容旧调用；M3 起不再添加机器前缀
    _ = with_prefix
    body = build_advisor_reply(
        claims,
        query=query,
        followups=followups,
        report_hint=translate_terms(report_hint) if report_hint else None,
    )
    return _ensure_reply(body)


def _template_reply(intent: str, data: dict, with_prefix: bool = False) -> str:
    """兼容旧接口：优先 data['claims']，否则用 message。"""
    _ = with_prefix
    if data.get("claims"):
        claims = [Claim.model_validate(c) if isinstance(c, dict) else c for c in data["claims"]]
        return _template_from_claims(
            claims,
            data.get("followups") or [],
            with_prefix=False,
            report_hint=data.get("report_hint"),
            query=data.get("query") or data.get("user_query"),
        )
    from app.services.plain_language import translate_terms

    if data.get("message"):
        return _ensure_reply(translate_terms(str(data["message"])))
    if data.get("conclusions"):
        text = "\n".join(translate_terms(str(x)) for x in data["conclusions"])
        fus = data.get("followups") or []
        if fus:
            text += "\n\n（下方按钮可继续追问）"
        return _ensure_reply(text)
    return _ensure_reply(
        "你好，我是明鉴风控顾问。可以直接问：这家能贷吗？信用怎么样？哪里不对劲？哪里可疑要查？"
    )


def _llm_completion_params() -> tuple[str, dict]:
    model = (os.getenv("LLM_MODEL") or "deepseek-v4-pro").strip()
    params: dict = {"api_key": (os.getenv("LLM_API_KEY") or "").strip()}
    base = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").strip().rstrip("/")
    if base:
        params["api_base"] = base
        if not model.startswith(("openai/", "azure/", "gemini/", "zhipu/", "zai/", "deepseek/")):
            model = f"openai/{model}"
    return model, params


def _llm_extra_body(model: str) -> dict | None:
    if "deepseek" in model.lower():
        return {"thinking": {"type": "disabled"}}
    return None


# ── M1：通义点金金融解读层 ──
def _llm_financial_params() -> tuple[str, dict]:
    """通义点金模型参数（金融解读层专用）。

    优先读 FINANCIAL_LLM_* 环境变量，回退到主 LLM 配置。
    """
    model = (os.getenv("FINANCIAL_LLM_MODEL") or "").strip()
    key = (os.getenv("FINANCIAL_LLM_API_KEY") or "").strip()
    base = (os.getenv("FINANCIAL_LLM_BASE_URL") or "").strip()
    if not model:
        # 未配置金融模型时回退到主模型
        return _llm_completion_params()
    params: dict = {"api_key": key or (os.getenv("LLM_API_KEY") or "").strip()}
    if base:
        params["api_base"] = base.rstrip("/")
    if not model.startswith(("openai/", "azure/", "gemini/", "zhipu/", "zai/", "qwen/")):
        model = f"openai/{model}"
    return model, params


def financial_llm_available() -> bool:
    """M1：金融解读层 LLM 是否已配置且可用。"""
    model = (os.getenv("FINANCIAL_LLM_MODEL") or "").strip()
    key = (os.getenv("FINANCIAL_LLM_API_KEY") or "").strip()
    if not model or not key:
        return False
    from app.services import rate_limiter
    return rate_limiter.check_llm_limit()


class FinancialInterpPlan(BaseModel):
    """通义点金结构化输出：禁止任何数字；句数不限（按结论密度自然展开）。"""

    sentences: list[str] = Field(default_factory=list, max_length=16)


async def generate_financial_interpretation(
    claims: list[Claim],
    context: dict | None = None,
) -> str | None:
    """通义点金金融解读——只解释已有 Claim，不新增数字；供 DeepSeek 校验层引用。"""
    if not financial_llm_available():
        return None
    kept = filter_claims(claims)
    claim_lines = [c.claim for c in kept if c.claim]
    if not claim_lines:
        return None
    ctx = context or {}
    industry = ctx.get("industry_l1") or ""
    scope = ctx.get("scope") or "cohort"
    scenario = ctx.get("scenario")
    from app.services.persona import build_persona_prompt

    persona = build_persona_prompt(scenario)
    system = (
        persona + "\n"
        "你是金融风控解读专家。根据给定的风控结论，用中文给出带金融因果的解读。\n"
        "规则：\n"
        "1. 禁止出现任何数字（阿拉伯数字与百分号）。只用定性描述（偏低/偏高/承压/稳健）\n"
        "2. 输出若干句（按结论密度自然展开），建议以「因为…所以…」或「这表明…」的因果结构组织\n"
        "3. 使用金融专业术语，但要让非专业人士能理解\n"
        "4. 不要重复结论原文，而是给出「为什么」和「意味着什么」\n"
        "5. 禁用 AI 套话（如：值得注意的是、需要指出的是）\n"
        "6. 禁止计算或推导任何新数字"
    )
    user = (
        f"{'行业：' + industry if industry else ''}\n"
        f"{'分析范围：' + ('单企业' if scope == 'individual' else '群体/行业')}\n"
        f"引擎结论（唯一事实来源）：\n" + "\n".join(f"- {line}" for line in claim_lines[:8])
    )
    try:
        raw_text: str | None = None
        # 优先 instructor 结构化
        try:
            model, params = _llm_financial_params()
            import instructor
            from openai import OpenAI

            api_key = params.get("api_key") or ""
            base_url = params.get("api_base")
            client_kwargs: dict = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            client = instructor.from_openai(OpenAI(**client_kwargs))
            plan = client.chat.completions.create(
                model=model.replace("openai/", "") if model.startswith("openai/") else model,
                response_model=FinancialInterpPlan,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=300,
                temperature=0.3,
            )
            if plan and plan.sentences:
                raw_text = "".join(s.strip() for s in plan.sentences if s and s.strip())
        except Exception as exc:
            logger.info("financial instructor unavailable, litellm fallback: %s", exc)

        if not raw_text:
            model, params = _llm_financial_params()
            import litellm

            response = litellm.completion(
                model=model,
                **params,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=300,
                temperature=0.3,
                timeout=30,
            )
            raw_text = _extract_llm_content(response)

        if not raw_text:
            return None
        # 硬规则：金融层句子不得含数字
        sentences = re.split(r"(?<=[。！？])", raw_text)
        kept_sentences = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if re.search(r"\d", s):
                logger.info("drop financial interp sentence with digit: %r", s[:60])
                continue
            kept_sentences.append(s)
        result = "".join(kept_sentences).strip()
        _record_llm_usage()
        return result or None
    except Exception as exc:
        logger.warning("financial interpretation failed: %s", exc)
        return None


def _extract_llm_content(response) -> str:
    if not response or not getattr(response, "choices", None):
        return ""
    message = response.choices[0].message
    content = getattr(message, "content", None)
    if content is None:
        content = getattr(message, "reasoning_content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(part))
        content = "".join(parts)
    if not isinstance(content, str):
        content = str(content) if content is not None else ""
    content = content.strip()
    if not content:
        reasoning = getattr(message, "reasoning_content", None)
        if isinstance(reasoning, str) and reasoning.strip():
            content = reasoning.strip()
    return content


def _sanitize_narration(text: str, claims: list[Claim]) -> str:
    """报告解读段：拆句后丢弃引入未授权数字的句子，及全达标章的风险方向话术。

    双重校验（claim 唯一化铁律）：
    1) 数字锚点——句中数字必须能在给定 claim 中找到；
    2) 结论方向——全达标章（无任何风险结论）不得出现「承压/越线/预警」等风险措辞，
       否则复现「指标达标却说偿债承压」的文字与数据打架。
    """
    from app.services.report_templates import sanitize_surface_industry_terms

    allowed_claims = filter_claims(claims)
    allowed = collect_allowed_numbers(allowed_claims)
    has_risk = claims_have_risk_verdict(allowed_claims)
    kept_sentences: list[str] = []
    for sentence in re.split(r"(?<=[。！？；])", text or ""):
        s = sentence.strip()
        if not s:
            continue
        if not sentence_has_anchor(s, allowed):
            logger.info("drop hallucinated narration sentence: %r", s[:60])
            continue
        if not has_risk and sentence_has_risk_direction(s):
            logger.info("drop risk-direction narration on达标 chapter: %r", s[:60])
            continue
        kept_sentences.append(sanitize_surface_industry_terms(s))
    return "".join(kept_sentences).strip()


def materialize_plan_sentences(sentences: list[str], claims: list[Claim]) -> str | None:
    """A.4：把 schema 句列表拼成表面文本，再过数字/方向 sanitize；全丢则弃权。"""
    parts: list[str] = []
    for raw in sentences or []:
        s = (raw or "").strip()
        if not s:
            continue
        if not s.endswith(("。", "！", "？", "；")):
            s += "。"
        parts.append(s)
    if not parts:
        return None
    cleaned = _sanitize_narration("".join(parts), claims)
    return cleaned or None


def _tone_prompt(tone: dict | None) -> str:
    """L2 语气：注入统一 PERSONA + 场景变体（红线 §4）。

    所有 LLM 调用必须携带 persona；tone=None 时仍返回基础 PERSONA prompt。
    tone 携带 scenario 时，persona prompt 自动叠加对应语气变体（TONE_VARIANTS）。
    tone 单独传 persona 字段（无 scenario）时，作为附加身份行注入，确保旧调用方
    的自定义 persona 不丢失。
    """
    from app.services.persona import build_persona_prompt

    if tone is None:
        return build_persona_prompt(None)

    scenario = tone.get("scenario")
    base = build_persona_prompt(scenario)
    extras: list[str] = []
    # tone.persona 与 base 的「当前角色」不同时，作为附加身份保留（如报告定制身份）
    if tone.get("persona") and tone["persona"] not in base:
        extras.append(f"补充身份：{tone['persona']}。")
    if tone.get("style") and tone["style"] not in base:
        extras.append(f"补充文风：{tone['style']}。")
    if extras:
        return base + " " + " ".join(extras)
    return base


async def generate_narration(title: str, claims: list[Claim], tone: dict | None = None) -> str | None:
    """报告章节解读：A.4 schema 句列表润色；失败则弃权（不回落自由散文顶替）。

    DeepSeek Chat 仅保证 json_object 语法，不保证 token 级 schema——本地用
    NarrationPlan + sanitize 硬约束；不引入 Outlines（需自托管推理）。
    """
    if not llm_available():
        return None
    kept = filter_claims(claims)
    claim_lines = [c.claim for c in kept if c.claim]
    if not claim_lines:
        return None
    system = (
        "你只做表面润色：把给定结论改写成中文解读（句数不限，按结论密度自然展开；"
        "禁止写成执行摘要，禁止逐条罗列各类信号命中家数——数字已在关键数字表中）。"
        "必须输出 JSON 对象，格式严格为 {\"sentences\":[\"句1\",\"句2\",...]}。"
        "开篇给风险结论方向（承压/稳健/越线/达标），可用一两处关键数字点睛；"
        "收尾给可执行建议。"
        "禁用内部开发词（如「积木」），改用「预警类型/信号类型」。"
        "只能使用给定结论中的数字与事实，禁止新增任何数字、企业名或未经给定的事实。"
        + _tone_prompt(tone)
    )
    user = f"章节标题：{title}\n给定结论（唯一事实来源）：\n" + "\n".join(
        f"- {line}" for line in claim_lines
    )
    plan = await _structured_response(
        system, user, NarrationPlan, '{"sentences":["解读句1","解读句2"]}'
    )
    if isinstance(plan, NarrationPlan) and plan.sentences:
        return materialize_plan_sentences(plan.sentences, kept)
    logger.info("narration schema path empty/failed, abstain (no free-text fallback)")
    return None


async def generate_executive_summary(
    kpis: list[dict[str, str]],
    chapter_titles: list[str],
    claims: list[Claim],
    tone: dict | None = None,
) -> str | None:
    """报告执行摘要：A.4 schema 句列表；失败弃权，不自由散文顶替。"""
    if not llm_available():
        return None
    kept = filter_claims(claims)
    claim_lines = [c.claim for c in kept if c.claim][:12]
    fact_lines = [f"{k.get('label', '')}{k.get('value', '')}{k.get('unit', '')}" for k in kpis]
    system = (
        "你只做表面润色：概括报告全文（句数不限，按报告密度自然展开；"
        "开篇给整体风险判断，中段点出最需关注的风险点，收尾给可执行建议）。"
        "必须输出 JSON 对象，格式严格为 {\"sentences\":[\"句1\",\"句2\",...]}。"
        "只能使用给定的事实与结论，禁止新增任何数字、企业名或未经给定的事实。"
        + _tone_prompt(tone)
    )
    user = (
        "报告章节：" + "、".join(chapter_titles) + "\n"
        "关键指标：" + "；".join(fact_lines) + "\n"
        "给定结论（唯一事实来源）：\n" + "\n".join(f"- {line}" for line in claim_lines)
    )
    plan = await _structured_response(
        system, user, SummaryPlan, '{"sentences":["摘要句1","摘要句2"]}'
    )
    if isinstance(plan, SummaryPlan) and plan.sentences:
        return materialize_plan_sentences(plan.sentences, kept)
    logger.info("executive summary schema path empty/failed, abstain")
    return None


def _record_llm_usage() -> None:
    """计入每日 LLM 配额（仅用户对话级调用，不含报告章节解读等内部补全）。"""
    from app.services import rate_limiter

    rate_limiter.increment()


async def _plain_completion(
    system: str, user: str, *, max_tokens: int = 300, temperature: float = 0.2
) -> str:
    """单次非结构化 LLM 补全，只取 content（不取 reasoning），失败返回空串。"""
    if not llm_available():
        return ""
    model, llm_params = _llm_completion_params()
    try:
        import litellm

        kwargs: dict = {
            "model": model,
            **llm_params,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": 40,
        }
        extra = _llm_extra_body(model)
        if extra:
            kwargs["extra_body"] = extra
        response = litellm.completion(**kwargs)
        if not response or not getattr(response, "choices", None):
            return ""
        message = response.choices[0].message
        content = getattr(message, "content", None)
        if isinstance(content, list):
            content = "".join(
                str(p.get("text") or p.get("content") or "") if isinstance(p, dict) else str(p)
                for p in content
            )
        text = (content or "").strip()
        return text
    except Exception as exc:
        logger.warning("plain completion failed: %s", exc)
        return ""


async def classify_intent_llm(query: str) -> dict | None:
    """发散问题兜底：LLM 把问题映射到固定 功能×维度，失败返回 None。"""
    if not llm_available():
        return None
    from app.services.intent_engine import DIMENSIONS, FUNCTIONS, industry_l1_options

    industries = "、".join(industry_l1_options())
    from app.services.persona import build_persona_prompt
    persona = build_persona_prompt(None)
    system = (
        persona + "\n"
        "你是意图分类器，把用户问题映射到固定组合。"
        "function 只能从 [score, authenticity, fraud, benchmark, trend, report, email_report, signal, general] 选；"
        "dimension 只能从 [overall, industry, region, time, signal] 选；"
        f"industry_l1 从 [{industries}] 识别，无则 null。"
        '只输出 JSON，例如 {"function":"trend","dimension":"industry","industry_l1":null}'
    )
    text = await _plain_completion(system, f"用户问题：{query}", max_tokens=120)
    if not text:
        return None
    try:
        import json

        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0) if m else text)
        fn = str(data.get("function") or "general")
        dim = str(data.get("dimension") or "overall")
        if fn not in FUNCTIONS:
            fn = "general"
        if dim not in DIMENSIONS:
            dim = "overall"
        ind = data.get("industry_l1")
        return {
            "function": fn,
            "dimension": dim,
            "industry_l1": ind if isinstance(ind, str) and ind else None,
            "confidence": 0.72,
        }
    except Exception as exc:
        logger.warning("classify_intent_llm parse failed: %s", exc)
        return None


async def generate_claim_reply(
    query: str,
    claims: list[Claim],
    followups: list[str],
    *,
    report_hint: str | None = None,
    persona: dict | None = None,
    financial_interp: str | None = None,
) -> tuple[str, ClaimBundle, str]:
    """DeepSeek 校验润色层：Claims(+可选金融因果参考) → 大白话。reply_source ∈ {llm,template}。"""
    from app.services.hallucination_guard import apply_chat_hallucination_guard
    from app.services.persona import build_persona_prompt
    from app.services.plain_language import (
        build_advisor_reply,
        detect_scenario,
        scenario_system_prompt,
        translate_terms,
    )

    kept = filter_claims(claims)
    seed = ClaimBundle(
        conclusions=[c.claim for c in kept],
        followups=list(followups)[:3],
        report_hint=report_hint,
    )
    scenario = detect_scenario(query)
    persona_scenario = scenario
    if isinstance(persona, dict) and persona.get("scenario") in ("loan", "rating", "warn", "audit", None):
        # 会话 scenario 优先（含 None→默认人格）
        if "scenario" in persona:
            persona_scenario = persona.get("scenario")

    if not llm_available():
        reply = build_advisor_reply(
            kept,
            query=query,
            followups=seed.followups,
            report_hint=report_hint,
        )
        return _ensure_reply(reply), seed, "template"

    claim_payload = [
        {
            "claim": translate_terms(c.claim),
            "value": c.value.model_dump() if c.value else None,
            "confidence": c.confidence,
        }
        for c in kept
    ]

    system = scenario_system_prompt(scenario) + " 输出 conclusions、followups（追问建议）、可选 report_hint。"
    if persona:
        persona_prompt = build_persona_prompt(persona_scenario)
        system = persona_prompt + "\n" + system
    user = (
        f"用户问题：{query}\n"
        f"场景侧重：{scenario}\n"
        f"给定结论（唯一事实来源）：{json.dumps(claim_payload, ensure_ascii=False)}\n"
        f"建议追问：{json.dumps(followups[:5], ensure_ascii=False)}"
    )
    if financial_interp:
        user += (
            f"\n金融因果参考（只可融入措辞，禁止新增任何数字或事实）：{financial_interp}\n"
        )

    try:
        bundle = await _instructor_bundle(system, user)
        if bundle is None:
            raise RuntimeError("instructor unavailable")
        conclusions = _sanitize_conclusions(bundle.conclusions or [], kept) or [
            translate_terms(c.claim) for c in kept
        ]
        conclusions = [translate_terms(s) for s in conclusions]
        if len(conclusions) < 2:
            raise RuntimeError("advisor structure too short")
        fus = (bundle.followups or followups)[:3]
        hint = bundle.report_hint or report_hint
        # report_hint 内数字必须过闸
        if hint:
            _, hint, _ = apply_chat_hallucination_guard("", kept, report_hint=translate_terms(hint), followups=[])
        out = ClaimBundle(conclusions=conclusions, followups=fus, report_hint=hint)
        text = "\n".join(out.conclusions)
        if hint:
            text += "\n" + hint
        if fus:
            text += "\n\n（下方按钮可继续追问）"
        if "规则模板生成" in text:
            text = text.replace("[规则模板生成]", "").replace("规则模板生成", "").strip()
        _record_llm_usage()
        return _ensure_reply(text), out, "llm"
    except Exception as exc:
        logger.warning("structured LLM failed: %s", exc)
        reply = build_advisor_reply(
            kept,
            query=query,
            followups=followups,
            report_hint=report_hint,
        )
        return _ensure_reply(reply), seed, "template"


async def _structured_response(system: str, user: str, response_model, json_hint: str):
    """通用结构化输出：instructor 优先，失败回退 litellm JSON 模式 + model_validate_json。

    供 ClaimBundle（对话结论）与 CustomReportTurn（定制对话）共用。
    """
    model, llm_params = _llm_completion_params()
    try:
        import instructor
        from openai import OpenAI

        api_key = llm_params.get("api_key") or ""
        base = llm_params.get("api_base") or "https://api.deepseek.com"
        # litellm 用 openai/ 前缀；instructor OpenAI 客户端用裸模型名
        raw_model = (os.getenv("LLM_MODEL") or "deepseek-v4-pro").strip()
        if raw_model.startswith("openai/"):
            raw_model = raw_model[len("openai/") :]

        client = instructor.from_openai(OpenAI(api_key=api_key, base_url=base))
        kwargs: dict = {
            "model": raw_model,
            "response_model": response_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_retries": 2,
            "temperature": 0.1,
        }
        extra = _llm_extra_body(raw_model)
        if extra:
            kwargs["extra_body"] = extra
        return client.chat.completions.create(**kwargs)
    except Exception as e1:
        logger.info("instructor path failed (%s), try litellm json", e1)

    try:
        import litellm

        completion_kwargs: dict = {
            "model": model,
            **llm_params,
            "messages": [
                {"role": "system", "content": system + f" 请只输出 JSON：{json_hint}。"},
                {"role": "user", "content": user},
            ],
            "max_tokens": 600,
            "temperature": 0.1,
            "timeout": 45,
            "response_format": {"type": "json_object"},
        }
        extra = _llm_extra_body(model)
        if extra:
            completion_kwargs["extra_body"] = extra
        response = litellm.completion(**completion_kwargs)
        raw = _extract_llm_content(response)
        return response_model.model_validate_json(raw)
    except Exception as e2:
        logger.warning("litellm json fallback failed: %s", e2)
        return None


async def _instructor_bundle(system: str, user: str) -> ClaimBundle | None:
    return await _structured_response(system, user, ClaimBundle, "conclusions, followups, report_hint")


async def llm_custom_report_turn(state: dict) -> "object | None":
    """定制报告对话单轮：让 LLM 判断「继续问一个问题」还是「产出方案」。

    只填充结构/范围/标题/语气槽位，不产生任何数字或事实（铁律）。失败返回 None（降级规则梯）。
    """
    if not llm_available():
        return None
    from app.schemas.custom_report import CustomReportTurn
    from app.services.intent_engine import industry_l1_options, province_options
    from app.services.report_templates import CHAPTER_REGISTRY, CUSTOM_CHAPTERS

    chapters_vocab = "；".join(f"{k}:{entry['desc']}" for k, entry in CHAPTER_REGISTRY.items())
    industries = "、".join(industry_l1_options())
    provinces = "、".join(province_options())

    spec = state.get("spec") or {}
    # 已确定槽位（规则侧累计 + LLM 前几轮推断）：只展示章节/行业/地区，避免 LLM 反复追问已回答项
    determined = ""
    if spec:
        det_names = "、".join(
            CHAPTER_REGISTRY[c]["title"] for c in (spec.get("chapters") or []) if c in CHAPTER_REGISTRY
        )
        det_parts: list[str] = []
        if det_names:
            det_parts.append(f"章节:{det_names}")
        if spec.get("industry_l1"):
            det_parts.append(f"行业:{spec['industry_l1']}")
        if spec.get("province"):
            det_parts.append(f"地区:{spec['province']}")
        if spec.get("enterprises"):
            det_parts.append(f"企业:{'、'.join(spec['enterprises'])}")
        determined = "；".join(det_parts) or "（暂未确定任何槽位）"
    else:
        determined = "（暂未确定任何槽位）"

    system = (
        "你是明鉴风控报告的定制顾问。定制本意是：从用户对话识别场景意图，"
        "再组合相应章节生成报告——不是把用户锁死在「画像/预警」两快捷模板里。"
        f"可组合章节（key:说明）：{chapters_vocab}。"
        f"行业白名单：[{industries}]；地区白名单：[{provinces}]。"
        "规则："
        "1) 一次只问一个简短问题；优先弄清「想解决什么风险/关注什么」以选定 chapters；"
        "2) chapters 可从上述全部 key 自由有序组合（财务/税务/发票/真实性/信号/评分/对标/趋势均可）；"
        "3) industry_l1 / province / enterprises 只决定数据范围滤镜，不要用范围去删减已识别的章节；"
        "4) 根据已有信息推断 chapters、industry_l1、province、enterprises、title、purpose；"
        "5) chapters 与诉求基本对齐就 propose=true；enterprises 只填明确的「企业N」；"
        "industry_l1/province 只从白名单取值，无则 null。"
        "只输出 JSON："
        '{next_question, propose, spec:{chapters, industry_l1, province, enterprises, title, tone, purpose}}。'
    )
    user = (
        f"已确定的槽位：{determined}\n"
        f"已收集的诉求：{state.get('purpose') or '（空）'}\n"
        f"已进行轮次：{state.get('turn', 0)}\n"
        f"用户最新回答：{state.get('last_answer') or '（开始定制）'}"
    )
    return await _structured_response(system, user, CustomReportTurn, "next_question, propose, spec")


async def generate_reply(query: str, intent: str, data: dict) -> str:
    """兼容旧 chat 路径。"""
    from app.services.hallucination_guard import apply_chat_hallucination_guard

    if data.get("claims"):
        claims = [Claim.model_validate(c) if isinstance(c, dict) else c for c in data["claims"]]
        reply, _, _ = await generate_claim_reply(
            query,
            claims,
            data.get("followups") or [],
            report_hint=data.get("report_hint"),
        )
        reply, _, _ = apply_chat_hallucination_guard(reply, claims)
        return reply
    if not llm_available():
        return _template_reply(intent, data, with_prefix=False)
    try:
        import litellm

        model, llm_params = _llm_completion_params()
        summary = json.dumps(
            {k: v for k, v in data.items() if k not in ("claims", "charts")},
            ensure_ascii=False,
            default=str,
        )[:800]
        completion_kwargs: dict = {
            "model": model,
            **llm_params,
            "messages": [
                {
                    "role": "system",
                    "content": "你是风控分析引擎。根据数据用中文概括，不要编造数字。",
                },
                {"role": "user", "content": f"问题：{query}\n意图：{intent}\n数据：{summary}"},
            ],
            "max_tokens": 250,
            "temperature": 0.2,
            "timeout": 45,
        }
        extra = _llm_extra_body(model)
        if extra:
            completion_kwargs["extra_body"] = extra
        response = litellm.completion(**completion_kwargs)
        raw = _extract_llm_content(response)
        if not raw:
            return _template_reply(intent, data, with_prefix=False)
        _record_llm_usage()
        # 无 Claim：剥离一切含数字句子
        gated, _, _ = apply_chat_hallucination_guard(raw[:400], [])
        return _ensure_reply(gated)
    except Exception as exc:
        logger.warning("LLM reply failed: %s", exc)
        return _template_reply(intent, data, with_prefix=False)
