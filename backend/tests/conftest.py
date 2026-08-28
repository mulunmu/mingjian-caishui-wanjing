import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "llm: optional LLM integration (requires LLM_API_KEY)")


@pytest.fixture
def llm_api_key():
    key = os.getenv("LLM_API_KEY", "")
    if not key or key == "your-api-key-here":
        pytest.skip("LLM_API_KEY not configured")
    return key
