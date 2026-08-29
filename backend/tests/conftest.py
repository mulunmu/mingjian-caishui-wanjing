import os

import pytest


def pytest_configure(config):
    # 单测默认关闭鉴权，避免模块 import 时 AUTH_REQUIRED 代码默认 true 拖垮契约测试
    os.environ.setdefault("AUTH_REQUIRED", "false")
    config.addinivalue_line("markers", "llm: optional LLM integration (requires LLM_API_KEY)")


@pytest.fixture
def llm_api_key():
    key = os.getenv("LLM_API_KEY", "")
    if not key or key == "your-api-key-here":
        pytest.skip("LLM_API_KEY not configured")
    return key
