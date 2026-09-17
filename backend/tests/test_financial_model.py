from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.claim import Claim, ClaimValue
from app.services import financial_model, llm_reply


def test_financial_model_uses_dedicated_config(monkeypatch):
    monkeypatch.setenv("FINANCIAL_LLM_MODEL", "finance-model")
    monkeypatch.setenv("FINANCIAL_LLM_API_KEY", "secret")
    monkeypatch.setenv("FINANCIAL_LLM_BASE_URL", "https://finance.example/v1")
    config = financial_model.load_financial_model_config()
    assert config.available is True
    assert config.model == "finance-model"
    assert config.source == "dedicated"
    assert config.api_key_configured is True
    assert "secret" not in str(config)


def test_financial_model_falls_back_to_api_baseline(monkeypatch):
    monkeypatch.delenv("FINANCIAL_LLM_MODEL", raising=False)
    monkeypatch.delenv("FINANCIAL_LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL", "main-model")
    monkeypatch.setenv("LLM_API_KEY", "main-secret")
    config = financial_model.load_financial_model_config()
    assert config.available is True
    assert config.model == "main-model"
    assert config.source == "main_api_baseline"


@pytest.mark.asyncio
async def test_financial_interpretation_uses_async_instructor(monkeypatch):
    monkeypatch.setenv("FINANCIAL_LLM_MODEL", "finance-model")
    monkeypatch.setenv("FINANCIAL_LLM_API_KEY", "secret")

    async def fake_completion(system, user, response_model, **kwargs):
        assert "digital" in system.lower() or "数字" in system
        assert response_model.__name__ == "FinancialInterpPlan"
        return response_model(sentences=["因为现金流持续承压，所以短期偿债应保持谨慎。"])

    monkeypatch.setattr(llm_reply, "_async_instructor_completion", fake_completion)
    result = await llm_reply.generate_financial_interpretation(
        [Claim(claim="经营现金流净额为负。", value=ClaimValue(metric="cash_flow_net", number=-1, unit="元"))]
    )
    assert result == "因为现金流持续承压，所以短期偿债应保持谨慎。"


@pytest.mark.asyncio
async def test_financial_interpretation_drops_numeric_output(monkeypatch):
    monkeypatch.setenv("FINANCIAL_LLM_MODEL", "finance-model")
    monkeypatch.setenv("FINANCIAL_LLM_API_KEY", "secret")

    async def fake_completion(system, user, response_model, **kwargs):
        return response_model(sentences=["因为现金流为负 12 元，所以风险较高。"])

    monkeypatch.setattr(llm_reply, "_async_instructor_completion", fake_completion)
    result = await llm_reply.generate_financial_interpretation(
        [Claim(claim="经营现金流净额为负。", value=ClaimValue(metric="cash_flow_net", number=-1, unit="元"))]
    )
    assert result is None


@pytest.mark.asyncio
async def test_financial_interpretation_skips_without_model(monkeypatch):
    monkeypatch.delenv("FINANCIAL_LLM_MODEL", raising=False)
    monkeypatch.delenv("FINANCIAL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = await llm_reply.generate_financial_interpretation(
        [Claim(claim="经营现金流净额为负。", confidence="computed")]
    )
    assert result is None
