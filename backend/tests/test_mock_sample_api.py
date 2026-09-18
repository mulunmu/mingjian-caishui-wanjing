"""Mock 汇总数据结构（仅底层测试样本，不暴露生产 API）。"""
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
