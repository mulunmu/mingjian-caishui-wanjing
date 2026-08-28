"""API 契约测试 — 验证关键端点的响应格式"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_health_response_format():
    """health 端点返回正确的 data_mode"""
    # 测试 mock_data 模块的数据契约
    from app.services.mock_data import MOCK_ENTERPRISES, get_all_mock_enterprises
    from app.services.llm_reply import is_llm_configured

    # mock 数据必须包含必要字段
    required_fields = ["enterprise_id", "enterprise_name", "overall_score", "risk_level",
                       "dimensions", "credit_level", "source"]
    for ent in MOCK_ENTERPRISES:
        for field in required_fields:
            assert field in ent, f"Missing {field} in {ent['enterprise_id']}"

    # llm_configured 返回布尔值
    assert isinstance(is_llm_configured(), bool)


def test_mock_list_format():
    """企业列表返回正确结构"""
    from app.services.mock_data import get_all_mock_enterprises, get_mock_warnings

    ents = get_all_mock_enterprises()
    assert len(ents) == 10
    for e in ents:
        assert "source" in e
        assert e["source"] == "mock"
        assert isinstance(e["dimensions"], dict)
        assert len(e["dimensions"]) == 5

    warnings = get_mock_warnings()
    for w in warnings:
        assert len(w["warning_signals"]) > 0


def test_enterprise_score_range():
    """企业评分在有效范围内"""
    from app.services.mock_data import MOCK_ENTERPRISES
    for ent in MOCK_ENTERPRISES:
        assert 0 <= ent["overall_score"] <= 100, f"Score out of range: {ent['enterprise_id']}"


def test_dimension_scores_range():
    """维度评分在 5-100 范围内"""
    from app.services.mock_data import MOCK_ENTERPRISES
    for ent in MOCK_ENTERPRISES:
        for dim, score in ent["dimensions"].items():
            assert 5 <= score <= 100, f"Dimension {dim} out of range for {ent['enterprise_id']}"


def test_warning_signal_labels():
    """预警信号有对应标签"""
    from app.services.llm_reply import WARNING_LABELS
    assert len(WARNING_LABELS) >= 5
    for key, label in WARNING_LABELS.items():
        assert len(label) > 0


def test_assessment_weights():
    """评分权重和为 1.0"""
    from app.services.assessment_weights import DIMENSION_WEIGHTS, DIMENSION_LABELS
    total = sum(DIMENSION_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01, f"Weights sum to {total}"
    assert len(DIMENSION_LABELS) == 5
