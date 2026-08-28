"""LLM 结构化语义解析：NL → SemanticQuery（instructor 优先，litellm json 降级）。

规则层降级为前置过滤与校正器（见 semantic_query.correct_semantic_query）；
本模块是 LLM 优先路径——把自然语言解析成带槽位的语义查询，槽位约束到规范词汇。
"""
from __future__ import annotations

import json
import logging
import os

from app.schemas.semantic_query import SemanticQuery
from app.services import llm_reply

logger = logging.getLogger(__name__)

_QUERY_TYPES = [
    "lookup", "aggregation", "comparison", "trend", "ranking",
    "distribution", "segmentation", "correlation", "faq", "methodology",
]


def _build_parse_system(dictionary: dict | None, session_context: dict | None) -> str:
    from app.services.intent_engine import _PROVINCE_KW, industry_l1_options

    industries = "、".join(industry_l1_options())
    provinces = "、".join(sorted({prov for _, prov in _PROVINCE_KW}))
    allowed_metrics = (dictionary or {}).get("allowed_metrics") or []
    metrics = "、".join(allowed_metrics)
    prev_q = ""
    if session_context and session_context.get("last_semantic_query"):
        prev_q = json.dumps(session_context["last_semantic_query"], ensure_ascii=False)[:400]

    return (
        "你是语义查询解析器，把用户的自然语言问题解析成结构化 JSON。"
        f"query_type 只能从 [{', '.join(_QUERY_TYPES)}] 选："
        "lookup=单一取值，aggregation=汇总，comparison=两者/多者对比，trend=趋势，"
        "ranking=前N/后N排名，distribution=分布，segmentation=按维度拆分，"
        "correlation=两指标相关性，faq=产品使用问题，methodology=指标口径/算法如何计算。\n"
        f"metrics 只能从规范指标[{metrics}]选，未知指标置空。\n"
        "dimensions 只能从 [industry_l1, province, scale_label, time] 选。\n"
        f"filters 的 industry_l1 值从 [{industries}] 识别；province 值从 [{provinces}] 识别（深圳归广东）。\n"
        "compare 用于 comparison：dimension 取 industry_l1/province/scale_label，values 为对比对象列表。\n"
        "entities 只能取问题里字面出现的 ENT\\d+ 匿名编号，绝不编造企业名/税号/法人。\n"
        f"上一轮语义查询（追问时继承缺失槽位）：{prev_q or '无'}\n"
        "只输出 JSON，字段：query_type, metrics, dimensions, filters, compare, sort, limit, entities。"
    )


def _build_parse_user(query: str, session_context: dict | None) -> str:
    return f"用户问题：{query}"


async def parse_semantic_query(
    query: str,
    session_context: dict | None = None,
    *,
    dictionary: dict | None = None,
) -> SemanticQuery | None:
    """LLM 结构化解析 NL → SemanticQuery。未配置/失败返回 None（由调用方降级规则路径）。"""
    if not llm_reply.llm_available():
        return None
    system = _build_parse_system(dictionary, session_context)
    user = _build_parse_user(query, session_context)
    sq = await _instructor_semantic_query(system, user)
    if sq is not None:
        sq.raw_query = query
        sq.source = "llm"
    return sq


async def _instructor_semantic_query(system: str, user: str) -> SemanticQuery | None:
    """镜像 llm_reply._instructor_bundle：先 instructor 结构化，失败降级 litellm json。"""
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
            "response_model": SemanticQuery,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_retries": 2,
            "temperature": 0.1,
        }
        extra = llm_reply._llm_extra_body(raw_model)
        if extra:
            kwargs["extra_body"] = extra
        return client.chat.completions.create(**kwargs)
    except Exception as e1:
        logger.info("instructor semantic parse failed (%s), try litellm json", e1)

    try:
        import litellm

        completion_kwargs: dict = {
            "model": model,
            **llm_params,
            "messages": [
                {"role": "system", "content": system + " 只输出一个 JSON 对象。"},
                {"role": "user", "content": user},
            ],
            "max_tokens": 500,
            "temperature": 0.1,
            "timeout": 45,
            "response_format": {"type": "json_object"},
        }
        extra = llm_reply._llm_extra_body(model)
        if extra:
            completion_kwargs["extra_body"] = extra
        response = litellm.completion(**completion_kwargs)
        raw = llm_reply._extract_llm_content(response)
        return SemanticQuery.model_validate_json(raw)
    except Exception as e2:
        logger.warning("litellm semantic parse fallback failed: %s", e2)
        return None
