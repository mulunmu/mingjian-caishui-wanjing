"""LLM 结构化语义解析：未配置返回 None；instructor 路径；litellm json 降级；corrector 钳制。"""
import json
import sys
import os
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_parse_returns_none_when_unconfigured(monkeypatch):
    from app.services import llm_reply, llm_semantic_parser

    monkeypatch.setattr(llm_reply, "_is_llm_configured", lambda: False)
    result = await llm_semantic_parser.parse_semantic_query("广东和江苏信用分对比")
    assert result is None


@pytest.mark.asyncio
async def test_parse_instructor_path_sets_source_and_raw(monkeypatch):
    from app.schemas.semantic_query import SemanticQuery
    from app.services import llm_reply, llm_semantic_parser

    monkeypatch.setattr(llm_reply, "_is_llm_configured", lambda: True)

    async def fake_instructor(system, user):
        return SemanticQuery(query_type="ranking", metrics=["credit_score"], dimensions=["industry_l1"])

    monkeypatch.setattr(llm_semantic_parser, "_instructor_semantic_query", fake_instructor)

    sq = await llm_semantic_parser.parse_semantic_query("信用分前10的行业")
    assert sq is not None
    assert sq.query_type == "ranking"
    assert sq.source == "llm"
    assert sq.raw_query == "信用分前10的行业"


@pytest.mark.asyncio
async def test_instructor_litellm_json_fallback(monkeypatch):
    from app.services import llm_reply, llm_semantic_parser

    monkeypatch.setattr(llm_reply, "_is_llm_configured", lambda: True)
    monkeypatch.setattr(
        llm_reply,
        "_llm_completion_params",
        lambda: ("openai/test-model", {"api_key": "k", "api_base": "https://example.com"}),
    )
    monkeypatch.setattr(llm_reply, "_llm_extra_body", lambda _m: None)
    # 令 instructor 导入失败 → 落入 litellm json 降级路径
    monkeypatch.setitem(sys.modules, "instructor", None)

    payload = {
        "query_type": "comparison",
        "metrics": ["credit_score"],
        "compare": [{"dimension": "province", "values": ["广东", "江苏"]}],
    }

    def fake_completion(**_kwargs):
        msg = MagicMock()
        msg.content = json.dumps(payload, ensure_ascii=False)
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    monkeypatch.setattr("litellm.completion", fake_completion)

    sq = await llm_semantic_parser._instructor_semantic_query("system", "user")
    assert sq is not None
    assert sq.query_type == "comparison"
    assert sq.compare[0].dimension == "province"
    assert sq.compare[0].values == ["广东", "江苏"]


def test_parse_system_prompt_constrains_slots():
    from app.services import llm_semantic_parser

    system = llm_semantic_parser._build_parse_system({"allowed_metrics": ["credit_score"]}, None)
    assert "query_type" in system
    assert "credit_score" in system
    assert "entities" in system
    assert "企业名" in system  # 脱敏约束在 prompt 内
