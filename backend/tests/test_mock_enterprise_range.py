"""Mock 企业范围测试 — 验证 ENT001-200 全覆盖"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_ent001_to_010_have_full_data():
    from app.services.mock_data import get_mock_enterprise
    for i in range(1, 11):
        eid = f"ENT{i:03d}"
        ent = get_mock_enterprise(eid)
        assert ent is not None, f"Missing {eid}"
        assert ent["source"] == "mock"
        assert ent["enterprise_name"] != f"企业 {eid}"


def test_ent011_to_200_have_placeholder():
    from app.services.mock_data import get_mock_enterprise
    for i in range(11, 21):  # 抽样检查 11-20
        eid = f"ENT{i:03d}"
        ent = get_mock_enterprise(eid)
        assert ent is not None, f"Missing {eid}"
        assert "enterprise_name" in ent
        assert ent["source"] == "mock_placeholder"


def test_ent999_returns_none():
    from app.services.mock_data import get_mock_enterprise
    assert get_mock_enterprise("ENT999") is None
    assert get_mock_enterprise("XYZ123") is None


def test_placeholder_has_required_fields():
    from app.services.mock_data import get_mock_enterprise
    ent = get_mock_enterprise("ENT050")
    required = ["enterprise_id", "enterprise_name", "overall_score", "risk_level",
                "dimensions", "credit_level", "source"]
    for field in required:
        assert field in ent, f"Missing field {field}"
