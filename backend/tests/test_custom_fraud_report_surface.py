"""定制发票舞弊报告：KPI 语义、积木禁词、结论去重。"""
from __future__ import annotations

from app.schemas.custom_report import CustomReportSpec
from app.services.custom_report import spec_to_report_spec
from app.services.report_templates import chapter_conclusion_lines, sanitize_surface_industry_terms
from app.services.slice_report import _build_summary_kpis, _compact_chapter_narrations


def test_build_summary_kpis_fraud_uses_firm_count_label():
    chapters = [
        {
            "function": "fraud",
            "meta": {"sample_count": 193, "flagged_count": 62},
            "claims": [],
        }
    ]
    kpis = _build_summary_kpis(chapters)
    by_label = {k["label"]: k for k in kpis}
    assert by_label["样本规模"]["value"] == "193"
    assert by_label["样本规模"]["unit"] == "家"
    assert "舞弊预警主体数" in by_label
    assert by_label["舞弊预警主体数"]["value"] == "62"
    assert by_label["舞弊预警主体数"]["unit"] == "家"
    assert "高风险/标记" not in by_label
    assert by_label["舞弊预警主体数"]["unit"] != "项"


def test_custom_fraud_spec_kpis():
    spec = CustomReportSpec(title="发票舞弊风险报告", chapters=["fraud"])
    out = spec_to_report_spec(spec)
    labels = [k["label"] for k in out["kpis"]]
    assert "舞弊预警主体数" in labels
    assert all(k.get("unit") != "项" or k.get("metric") == "fraud_signal_count" for k in out["kpis"])


def test_sanitize_replaces_yujing_jimu():
    assert "预警积木" not in sanitize_surface_industry_terms("集中度与进销错配是主要预警积木")
    assert "预警类型" in sanitize_surface_industry_terms("集中度与进销错配是主要预警积木")


def test_compact_narration_drops_signal_roster():
    chapters = [
        {
            "numeric_rows": [["预警主体数", "62", "家", "x"]],
            "narration": (
                "全库193家主体中62家呈现发票舞弊迹象，风险方向承压。"
                "信号命中分布为：进销错配22家、集中度27家、序列缺口9家、红字发票异常7家。"
                "集中度与进销错配是主要预警积木，优先调取购销合同与物流单据交叉验证。"
            ),
        }
    ]
    _compact_chapter_narrations(chapters)
    nar = chapters[0]["narration"]
    assert "预警积木" not in nar
    assert "预警类型" in nar or "交叉验证" in nar
    assert "序列缺口9家" not in nar


def test_conclusion_prefers_action_not_full_narration():
    lines = chapter_conclusion_lines(
        {
            "narration": (
                "全库193家主体中62家呈现发票舞弊迹象。信号命中分布为：进销错配22家、"
                "集中度27家、序列缺口9家。集中度与进销错配是主要预警类型，"
                "优先对这两类信号主体调取购销合同与物流单据交叉验证。"
            ),
            "numeric_rows": [["预警主体数", "62", "家", "x"]],
            "claims": [
                {
                    "claim": "全部主体 193 家，其中 62 家存在发票舞弊迹象，建议核查票据交易背景与货物凭证。"
                },
                {"claim": "信号「进销错配」命中 22 家主体。"},
            ],
        }
    )
    assert lines
    blob = "".join(lines)
    assert "建议" in blob or "调取" in blob or "核查" in blob
    assert "序列缺口9家" not in blob
