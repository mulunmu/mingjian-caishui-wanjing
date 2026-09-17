"""Financial model configuration without exposing credentials."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class FinancialModelConfig:
    provider: str
    model: str
    base_url: str
    source: str
    api_key_configured: bool
    available: bool

    def public_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url_configured": bool(self.base_url),
            "source": self.source,
            "api_key_configured": self.api_key_configured,
            "available": self.available,
        }


def load_financial_model_config() -> FinancialModelConfig:
    dedicated_model = (os.getenv("FINANCIAL_LLM_MODEL") or "").strip()
    model = dedicated_model or (os.getenv("LLM_MODEL") or "").strip()
    key = (
        (os.getenv("FINANCIAL_LLM_API_KEY") or "").strip()
        or (os.getenv("LLM_API_KEY") or "").strip()
    )
    base_url = (
        (os.getenv("FINANCIAL_LLM_BASE_URL") or "").strip()
        or (os.getenv("LLM_BASE_URL") or "").strip()
    )
    source = "dedicated" if dedicated_model else "main_api_baseline"
    provider = "openai_compatible"
    lowered = base_url.lower()
    if any(marker in lowered for marker in ("localhost", "127.0.0.1", "host.docker.internal", ":11434")):
        provider = "local_openai_compatible"
    return FinancialModelConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        source=source,
        api_key_configured=bool(key),
        available=bool(model and key),
    )
