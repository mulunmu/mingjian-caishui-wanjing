"""可选 LLM 集成测试：CI 无 key 时自动 skip。"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.llm_reply import classify_intent_llm, generate_narration, is_llm_configured
from app.schemas.claim import Claim, ClaimValue


@pytest.mark.llm
@pytest.mark.asyncio
async def test_classify_intent_llm_divergent_query(llm_api_key):
    assert is_llm_configured()
    result = await classify_intent_llm("这家企业是不是在搞骗贷套路")
    assert result is not None
    assert result.get("function") in {
        "fraud",
        "authenticity",
        "trend",
        "benchmark",
        "tax_health",
        "general",
    }


@pytest.mark.llm
@pytest.mark.asyncio
async def test_generate_narration_anchors_numbers(llm_api_key):
    # 结论含风险方向（承压）→ 本章允许风险措辞，解读段数字须锚定 47/193
    claims = [
        Claim(
            claim="样本 193 家，综合均分 47.0 分，整体承压。",
            value=ClaimValue(metric="avg_score", number=47.0, unit="分"),
            confidence="computed",
        )
    ]
    text = await generate_narration("概览", claims)
    assert text
    assert "47" in text or "193" in text
