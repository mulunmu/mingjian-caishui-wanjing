from __future__ import annotations

from app.schemas.custom_report import CustomReportSpec
from app.services.custom_report import proposed_blocks, spec_to_report_spec
from app.services.report_templates import CUSTOM_MODULE_REGISTRY


def test_custom_report_modules_are_categorized_and_sufficient():
    categories = {item.get("category") for item in CUSTOM_MODULE_REGISTRY.values()}
    assert len(CUSTOM_MODULE_REGISTRY) >= 14
    assert {"财务分析", "税务分析", "发票与交易", "真实性核验", "风险与评级", "对比与趋势"}.issubset(categories)


def test_module_specific_analysis_is_attached_to_plan():
    spec = CustomReportSpec(
        chapters=["solvency", "revenue_authenticity"],
        enterprises=[],
        title="测试报告",
        purpose="测试",
        chapter_analyses={"solvency": ["trend", "benchmark"], "revenue_authenticity": ["anomaly"]},
    )
    plan = spec_to_report_spec(spec)
    assert plan["chapters"][0]["function"] == "financial"
    assert plan["chapters"][0]["module_key"] == "solvency"
    assert plan["chapters"][0]["analysis_patterns"] == ["trend", "benchmark"]
    blocks = proposed_blocks(spec)
    assert blocks[0]["category"] == "财务分析"
    assert blocks[0]["analysis_patterns"] == ["trend", "benchmark"]
