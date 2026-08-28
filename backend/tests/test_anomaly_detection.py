"""差异驱动异动检测：洞察评级 → 异动标签 / 新增事件 / 实质异动判定。"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.core_metrics import LegalEvent
from app.services.anomaly_detection import (
    detect_anomalies,
    has_material_anomaly,
)
from app.services.insight_engine import Evidence, Insight


def _ins(rule_id="F-04", severity="预警", category="财务", title="营收显著下滑") -> Insight:
    return Insight(
        rule_id,
        category,
        title,
        severity,
        [Evidence("营收同比", -0.3, "", "core_metrics", "revenue_yoy")],
        "advice",
    )


def test_change_rule_maps_to_worse_than_prior():
    signals = detect_anomalies(None, None, [_ins()], [])
    assert len(signals) == 1
    s = signals[0]
    assert s["tag"] == "较上期恶化"
    assert s["level"] == "medium"
    assert s["trace"]["table"] == "core_metrics"
    assert s["trace"]["field"] == "revenue_yoy"


def test_high_insight_levels_high_and_keeps_tag():
    signals = detect_anomalies(None, None, [_ins(rule_id="T-01", severity="高危", category="税务", title="存在欠税")], [])
    assert signals[0]["level"] == "high"
    assert signals[0]["tag"] == "高危"


def test_legal_event_new_high_and_skip_out_of_window():
    recent = LegalEvent(id=1, enterprise_id="e1", event_type="tax_violation", severity="H",
                        event_date=datetime.now(timezone.utc), description="高严重度税务违法")
    old = LegalEvent(id=2, enterprise_id="e1", event_type="tax_audit", severity="M",
                     event_date=datetime(2020, 1, 1, tzinfo=timezone.utc), description="税务稽查")
    null_date = LegalEvent(id=3, enterprise_id="e1", event_type="tax_violation", severity="M",
                           event_date=None, description="税务违法")
    signals = detect_anomalies(None, None, [], [recent, old, null_date])
    by_id = {s["signal_id"]: s for s in signals}
    assert by_id["LEGAL-1"]["level"] == "high"
    assert by_id["LEGAL-1"]["tag"] == "新增"
    assert by_id["LEGAL-3"]["tag"] == "新增"  # 时效未知 → 保守标注「新增」
    assert "时效未知" in by_id["LEGAL-3"]["evidence"]
    assert "LEGAL-2" not in by_id  # 超回溯窗口的历史事件 → 跳过，不冒称「新增」


def test_empty_inputs_abstain():
    assert detect_anomalies(None, None, [], []) == []


def test_has_material_anomaly():
    high = detect_anomalies(None, None, [_ins(rule_id="T-01", severity="高危", category="税务", title="存在欠税")], [])
    assert has_material_anomaly(high) is True
    assert has_material_anomaly([]) is False
    medium = detect_anomalies(None, None, [_ins()], [])
    assert has_material_anomaly(medium, threshold=1) is True
    assert has_material_anomaly(medium, threshold=2) is False
