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

from app.schemas.claim import Claim, ClaimBundle, claims_to_public_reply, filter_claims
from app.services.hallucination_guard import (
    collect_allowed_numbers,
    filter_unanchored_sentences,
    sentence_has_anchor,
)

load_dotenv()

logger = logging.getLogger(__name__)

TEMPLATE_PREFIX = "[规则模板生成] "
FALLBACK_REPLY = TEMPLATE_PREFIX + "分析完成，请查看结论与追问建议。"

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
    with_prefix: bool = True,
    report_hint: str | None = None,
) -> str:
    prefix = TEMPLATE_PREFIX if with_prefix else ""
    body = claims_to_public_reply(claims, followups=None)
    if report_hint:
        body += "\n" + report_hint
    if followups:
        body += "\n\n可继续追问：" + "；".join(followups[:3])
    return _ensure_reply(prefix + body)


def _template_reply(intent: str, data: dict, with_prefix: bool = True) -> str:
    """兼容旧接口：优先 data['claims']，否则用 message。"""
    prefix = TEMPLATE_PREFIX if with_prefix else ""
    if data.get("claims"):
        claims = [Claim.model_validate(c) if isinstance(c, dict) else c for c in data["claims"]]
        return _template_from_claims(claims, data.get("followups") or [], with_prefix=with_prefix, report_hint=data.get("report_hint"))
    if data.get("message"):
        return _ensure_reply(prefix + str(data["message"]))
    if data.get("conclusions"):
        text = "\n".join(str(x) for x in data["conclusions"])
        fus = data.get("followups") or []
        if fus:
            text += "\n\n可继续追问：" + "；".join(fus[:3])
        return _ensure_reply(prefix + text)
    return _ensure_reply(
        prefix
        + "您好，我是风控分析助手。可提问：各行业趋势、真实性、舞弊、对标、预警或生成报告。"
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
    """报告解读段：拆句后丢弃引入未授权数字的句子。"""
    allowed_claims = filter_claims(claims)
    allowed = collect_allowed_numbers(allowed_claims)
    kept_sentences: list[str] = []
    for sentence in re.split(r"(?<=[。！？；])", text or ""):
        s = sentence.strip()
        if not s:
            continue
        if not sentence_has_anchor(s, allowed):
            logger.info("drop hallucinated narration sentence: %r", s[:60])
            continue
        kept_sentences.append(s)
    return "".join(kept_sentences).strip()


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


async def generate_narration(title: str, claims: list[Claim]) -> str | None:
    """报告章节解读段：锚定 computed 结论，禁止新增数字。失败返回 None。"""
    if not llm_available():
        return None
    kept = filter_claims(claims)
    claim_lines = [c.claim for c in kept if c.claim]
    if not claim_lines:
        return None
    system = (
        "你是风控报告解读助手。为报告章节写 2-3 句解读，说明该章节的发现与风险含义。"
        "只能使用给定结论中的数字与事实，禁止新增任何数字、企业名或未经给定的事实。"
    )
    user = f"章节标题：{title}\n给定结论（唯一事实来源）：\n" + "\n".join(
        f"- {line}" for line in claim_lines
    )
    text = await _plain_completion(system, user, max_tokens=220)
    if not text:
        return None
    cleaned = _sanitize_narration(text, kept)
    return cleaned or None


async def generate_executive_summary(
    kpis: list[dict[str, str]],
    chapter_titles: list[str],
    claims: list[Claim],
) -> str | None:
    """报告执行摘要：锚定 computed 结论与 KPI，禁止新增数字。失败返回 None。"""
    if not llm_available():
        return None
    kept = filter_claims(claims)
    claim_lines = [c.claim for c in kept if c.claim][:12]
    fact_lines = [f"{k.get('label', '')}{k.get('value', '')}{k.get('unit', '')}" for k in kpis]
    system = (
        "你是风控报告的执行摘要撰写者。用 3-5 句中文概括整份报告的核心发现、"
        "整体风险判断与建议关注点。只能使用给定的事实与结论，禁止新增任何数字、企业名或未经给定的事实。"
    )
    user = (
        "报告章节：" + "、".join(chapter_titles) + "\n"
        "关键指标：" + "；".join(fact_lines) + "\n"
        "给定结论（唯一事实来源）：\n" + "\n".join(f"- {line}" for line in claim_lines)
    )
    text = await _plain_completion(system, user, max_tokens=320)
    if not text:
        return None
    cleaned = _sanitize_narration(text, kept)
    return cleaned or None


async def classify_intent_llm(query: str) -> dict | None:
    """发散问题兜底：LLM 把问题映射到固定 功能×维度，失败返回 None。"""
    if not llm_available():
        return None
    from app.services.intent_engine import DIMENSIONS, FUNCTIONS, industry_l1_options

    industries = "、".join(industry_l1_options())
    system = (
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
) -> tuple[str, ClaimBundle, str]:
    """返回 (用户可见回复, ClaimBundle, reply_source)。reply_source ∈ {"llm","template"}。证据链不写入回复正文。"""
    kept = filter_claims(claims)
    seed = ClaimBundle(
        conclusions=[c.claim for c in kept],
        followups=list(followups)[:3],
        report_hint=report_hint,
    )

    if not llm_available():
        reply = _template_from_claims(kept, seed.followups, with_prefix=False, report_hint=report_hint)
        return reply, seed, "template"

    claim_payload = [
        {
            "claim": c.claim,
            "value": c.value.model_dump() if c.value else None,
            "confidence": c.confidence,
        }
        for c in kept
    ]

    system = (
        "你是风控分析助手。只能改写已给定结论的措辞，禁止新增任何数字或事实。"
        "输出 conclusions（改写后的结论句）、followups（追问建议）、可选 report_hint。"
        "若无法改写，原样返回给定结论。"
    )
    user = (
        f"用户问题：{query}\n"
        f"给定结论（唯一事实来源）：{json.dumps(claim_payload, ensure_ascii=False)}\n"
        f"建议追问：{json.dumps(followups[:5], ensure_ascii=False)}"
    )

    try:
        bundle = await _instructor_bundle(system, user)
        if bundle is None:
            raise RuntimeError("instructor unavailable")
        conclusions = _sanitize_conclusions(bundle.conclusions or [], kept) or [c.claim for c in kept]
        fus = (bundle.followups or followups)[:3]
        hint = bundle.report_hint or report_hint
        out = ClaimBundle(conclusions=conclusions, followups=fus, report_hint=hint)
        text = "\n".join(out.conclusions)
        if hint:
            text += "\n" + hint
        if fus:
            text += "\n\n可继续追问：" + "；".join(fus)
        _record_llm_usage()
        return _ensure_reply(text), out, "llm"
    except Exception as exc:
        logger.warning("structured LLM failed: %s", exc)
        reply = _template_from_claims(kept, followups, with_prefix=False, report_hint=report_hint)
        return reply, seed, "template"


async def _instructor_bundle(system: str, user: str) -> ClaimBundle | None:
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
            "response_model": ClaimBundle,
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
                {"role": "system", "content": system + " 请只输出 JSON：conclusions, followups, report_hint。"},
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
        return ClaimBundle.model_validate_json(raw)
    except Exception as e2:
        logger.warning("litellm json fallback failed: %s", e2)
        return None


async def generate_reply(query: str, intent: str, data: dict) -> str:
    """兼容旧 chat 路径。"""
    if data.get("claims"):
        claims = [Claim.model_validate(c) if isinstance(c, dict) else c for c in data["claims"]]
        reply, _, _ = await generate_claim_reply(
            query,
            claims,
            data.get("followups") or [],
            report_hint=data.get("report_hint"),
        )
        return reply
    if not llm_available():
        return _template_reply(intent, data, with_prefix=True)
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
                    "content": "你是风控分析助手。根据数据用中文概括，不要编造数字。",
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
            return _template_reply(intent, data, with_prefix=True)
        _record_llm_usage()
        return _ensure_reply(raw[:400])
    except Exception as exc:
        logger.warning("LLM reply failed: %s", exc)
        return _template_reply(intent, data, with_prefix=True)
