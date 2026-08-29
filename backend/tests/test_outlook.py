"""评级展望（L1 规则）单元测试：纯规则、可审计、趋势缺失弃权。"""
from app.services.outlook import OUTLOOK_LABELS, derive_outlook


def test_high_severity_forces_negative():
    r = derive_outlook(risk_level="中等风险", high_severity_cnt=1)
    assert r["outlook"] == "负面"


def test_high_risk_level_forces_negative():
    for level in ("高风险", "中高风险"):
        r = derive_outlook(risk_level=level, revenue_yoy=0.3, profit_yoy=0.3)
        assert r["outlook"] == "负面", level


def test_low_risk_is_positive():
    r = derive_outlook(risk_level="低风险")
    assert r["outlook"] == "正面"


def test_positive_trend_positive():
    r = derive_outlook(risk_level="中等风险", revenue_yoy=0.2, profit_yoy=0.1)
    assert r["outlook"] == "正面"


def test_trend_missing_abstains_to_stable():
    # 趋势数据缺失（None/0）→ 弃权（稳定），不硬判
    r = derive_outlook(risk_level="中等风险", revenue_yoy=None, profit_yoy=None)
    assert r["outlook"] == "稳定"


def test_single_positive_not_enough():
    # 只有营收正、净利润缺失 → 稳定
    r = derive_outlook(risk_level="中等风险", revenue_yoy=0.2, profit_yoy=None)
    assert r["outlook"] == "稳定"


def test_outlook_color_consistent():
    assert OUTLOOK_LABELS == {"正面": "#059669", "稳定": "#f57c00", "负面": "#dc2626"}
