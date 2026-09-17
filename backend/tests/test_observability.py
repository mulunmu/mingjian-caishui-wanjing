from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services import observability


def test_trace_middleware_sets_response_header(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    from app.main import app

    observability.reset_runtime_metrics()
    client = TestClient(app)
    response = client.get("/api/v1/health", headers={"X-Trace-Id": "trace-test-1"})
    assert response.status_code == 200
    assert response.headers["x-trace-id"] == "trace-test-1"
    metrics = observability.metrics_snapshot()
    assert any(key.startswith("http_requests_total|") for key in metrics["counters"])


def test_sentry_init_is_safe_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observability.init_sentry() is False
    assert observability.sentry_initialized() is False


@pytest.mark.asyncio
async def test_observability_endpoint_requires_admin(monkeypatch):
    from app.api.v1.observability import get_runtime_metrics
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await get_runtime_metrics(user={"role": "user"})
    assert exc.value.status_code == 403
    snapshot = await get_runtime_metrics(user={"role": "admin"})
    assert "counters" in snapshot
    assert "latency" in snapshot
