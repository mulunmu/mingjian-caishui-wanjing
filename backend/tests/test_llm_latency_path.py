from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.claim import Claim, ClaimBundle, ClaimValue
from app.services import dialog_act as da
from app.services import llm_reply


def _response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.asyncio
async def test_fast_claim_bundle_parses_fenced_json_without_retry(monkeypatch):
    calls: list[dict] = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return _response(
            '```json\n{"conclusions":["已由模型生成"],"followups":[],"report_hint":null}\n```'
        )

    monkeypatch.setattr(llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(
        llm_reply,
        "_llm_authoring_params",
        lambda: ("openai/deepseek-v4-flash", {"api_key": "test"}),
    )
    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    bundle = await llm_reply._fast_claim_bundle("system", "user")

    assert bundle is not None
    assert bundle.conclusions == ["已由模型生成"]
    assert len(calls) == 1
    assert calls[0]["max_retries"] == 0
    assert "JSON" in calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_fast_claim_bundle_rejects_empty_conclusions(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _response('{"conclusions":[],"followups":[],"report_hint":null}')

    monkeypatch.setattr(llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(
        llm_reply,
        "_llm_authoring_params",
        lambda: ("openai/deepseek-v4-flash", {"api_key": "test"}),
    )
    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    assert await llm_reply._fast_claim_bundle("system", "user") is None


@pytest.mark.asyncio
async def test_fast_claim_bundle_rejects_blank_conclusion(monkeypatch):
    async def fake_acompletion(**kwargs):
        return _response('{"conclusions":["   "],"followups":[],"report_hint":null}')

    monkeypatch.setattr(llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(
        llm_reply,
        "_llm_authoring_params",
        lambda: ("openai/deepseek-v4-flash", {"api_key": "test"}),
    )
    monkeypatch.setattr("litellm.acompletion", fake_acompletion)

    assert await llm_reply._fast_claim_bundle("system", "user") is None


@pytest.mark.asyncio
async def test_core_generation_escalates_to_one_pro_call_after_fast_failure(monkeypatch):
    calls: list[tuple[str, int]] = []

    async def fake_fast(system: str, user: str):
        return None

    async def fake_instructor(
        system: str,
        user: str,
        response_model,
        *,
        model_params,
        max_tokens,
        max_retries,
    ):
        model, _ = model_params
        calls.append((model, max_tokens))
        assert response_model.__name__ == "GeneratedClaimBundle"
        assert max_retries == 1
        return response_model(conclusions=["模型升级后生成"], followups=[], report_hint=None)

    monkeypatch.setattr(llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(llm_reply, "_fast_claim_bundle", fake_fast)
    monkeypatch.setattr(llm_reply, "_async_instructor_completion", fake_instructor)
    monkeypatch.setattr(
        llm_reply,
        "_llm_completion_params",
        lambda: ("openai/deepseek-v4-pro", {"api_key": "test"}),
    )

    reply, bundle, source = await llm_reply.generate_claim_reply(
        "资产负债率怎么样",
        [Claim(claim="资产负债率 60%。", value=ClaimValue(metric="debt_ratio", number=60, unit="%"))],
        [],
    )

    assert reply == "模型升级后生成"
    assert bundle.conclusions == ["模型升级后生成"]
    assert source == "llm"
    assert calls == [("openai/deepseek-v4-pro", 520)]


@pytest.mark.asyncio
async def test_core_generation_rejects_non_llm_claim_text_fallback(monkeypatch):
    async def fake_fast(system: str, user: str):
        return ClaimBundle(conclusions=["企业共有 999 家。"], followups=[])

    monkeypatch.setattr(llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(llm_reply, "_fast_claim_bundle", fake_fast)

    with pytest.raises(llm_reply.LLMGenerationError):
        await llm_reply.generate_claim_reply(
            "企业情况",
            [Claim(claim="营业收入 100 万元。", value=ClaimValue(metric="revenue", number=100, unit="万元"))],
            [],
        )


@pytest.mark.asyncio
async def test_dialog_classifier_uses_one_async_instructor_call(monkeypatch):
    calls: list[dict] = []

    async def fake_instructor(system, user, response_model, **kwargs):
        calls.append({"system": system, "user": user, "model": response_model, **kwargs})
        return da.DialogAct(act="meta_session", confidence=0.99)

    monkeypatch.setattr(llm_reply, "llm_available", lambda: True)
    monkeypatch.setattr(llm_reply, "_async_instructor_completion", fake_instructor)

    act = await da._llm_classify("你好", {})

    assert act is not None
    assert act.act == "meta_session"
    assert len(calls) == 1
    assert calls[0]["model"] is da.DialogAct
    assert calls[0]["max_tokens"] == 350


@pytest.mark.asyncio
async def test_async_instructor_completion_disables_hidden_retries(monkeypatch):
    calls: list[dict] = []

    class FakeCompletions:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return da.DialogAct(act="meta_session", confidence=0.99)

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("instructor.from_openai", lambda client: FakeClient())

    result = await llm_reply._async_instructor_completion(
        "system",
        "user",
        da.DialogAct,
        model_params=("openai/deepseek-v4-flash", {"api_key": "test"}),
        max_tokens=350,
        temperature=0.0,
    )

    assert result.act == "meta_session"
    assert calls[0]["max_retries"] == 0
    assert calls[0]["model"] == "deepseek-v4-flash"
