"""GET /risk/mock/sample 与 mock 汇总"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.mock_data import get_mock_sample_bundle, MOCK_ENTERPRISES


def test_mock_sample_bundle_shape():
    bundle = get_mock_sample_bundle()
    assert bundle["source"] == "mock"
    assert len(bundle["enterprises"]) == len(MOCK_ENTERPRISES)
    assert bundle["enterprises"][0]["enterprise_id"] == "ENT001"
    assert "display_label" in bundle["enterprises"][0]
    assert bundle["summary"]["sample_count"] == len(MOCK_ENTERPRISES)
    assert isinstance(bundle["warnings"], list)


def test_mock_sample_api():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    resp = client.get("/api/v1/risk/mock/sample")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "mock"
    assert len(data["enterprises"]) == 10
