"""Two-stage topic reference resolver: deterministic candidates, LLM tie-break."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable

from app.schemas.topic_state import TopicResolution, TopicSelection, TopicState


logger = logging.getLogger(__name__)


def _coerce_topic(value: TopicState | dict) -> TopicState:
    return value if isinstance(value, TopicState) else TopicState.model_validate(value)


def _default_llm_selector(
    reference: str,
    candidates: list[TopicState],
) -> dict | None:
    from app.services import llm_reply

    if not llm_reply.llm_available():
        return None
    try:
        import litellm

        model, params = llm_reply._llm_completion_params()
        candidate_text = "\n".join(
            f"- {item.topic_id} | 轮次={item.turn_index} | {item.summary} | "
            f"实体={item.entities} | 筛选={item.filters} | 指标={item.metrics}"
            for item in candidates
        )
        response = litellm.completion(
            model=model,
            **params,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是会话话题指代解析器。只能从候选 topic_id 中选择一个，"
                        "不得发明 ID。若无法确定，confidence 低于 0.6。"
                        "只输出 JSON：{\"topic_id\":\"...\",\"confidence\":0.0}。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"用户指代：{reference}\n候选主题：\n{candidate_text}",
                },
            ],
            max_tokens=120,
            temperature=0.0,
            timeout=15,
            response_format={"type": "json_object"},
        )
        raw = llm_reply._extract_llm_content(response)
        return json.loads(raw)
    except Exception as exc:
        logger.info("topic LLM selector unavailable: %s", exc)
        return None


def resolve_topic_candidates(
    reference: str,
    candidates: Iterable[TopicState | dict],
    *,
    llm_selector: Callable[[str, list[TopicState]], dict | None] | None = None,
    allow_llm: bool = True,
) -> TopicResolution:
    ranked = sorted(
        (_coerce_topic(item) for item in candidates),
        key=lambda item: (-item.score, -item.turn_index, item.topic_id),
    )
    if not ranked:
        return TopicResolution(status="not_found", reason="no_candidates")

    top = ranked[0]
    second_score = ranked[1].score if len(ranked) > 1 else 0.0
    gap = top.score - second_score
    if (top.score >= 0.85 and gap >= 0.08) or (top.score >= 0.58 and gap >= 0.12):
        return TopicResolution(
            status="resolved",
            topic=top,
            confidence=top.score,
            reason="deterministic_top",
        )

    selector = llm_selector if llm_selector is not None else _default_llm_selector
    if allow_llm:
        try:
            selected = selector(reference, ranked[:8])
            selection = TopicSelection.model_validate(selected) if selected else None
        except Exception as exc:
            logger.info("topic selector failed: %s", exc)
            selection = None
        if selection is not None:
            topic = next(
                (item for item in ranked if item.topic_id == selection.topic_id),
                None,
            )
            if topic is not None and selection.confidence >= 0.6:
                return TopicResolution(
                    status="resolved",
                    topic=topic,
                    confidence=selection.confidence,
                    reason="llm",
                )

    return TopicResolution(
        status="clarify",
        confidence=top.score,
        reason="ambiguous_reference",
        clarification_question=(
            "你指的是哪一个话题？请说具体一些，例如“刚才制造真实性那个”"
            "或“上上个问题”。"
        ),
    )
