"""报告 HTML 结构快照 — 锁定 WeasyPrint 模板关键区块（非像素级）"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.report_html import build_report_html


def _full_context():
    return {
        "scenario": "due_diligence",
        "scenario_label": "行业趋势风控",
        "tier": "standard",
        "title": "行业趋势风控报告",
        "story": "面向通识读者，讲清样本覆盖、行业走向与主要风险信号。",
        "report_date": "2026年08月27日",
        "summary_kpis": [
            {"label": "样本规模", "value": "193", "unit": "家"},
            {"label": "综合均分", "value": "47.0", "unit": "分"},
            {"label": "关注行业", "value": "制造", "unit": ""},
        ],
        "chapters": [
            {
                "title": "六维雷达 · 综合画像",
                "purpose": "样本六维均分雷达",
                "claims": [{"claim": "全样本综合均分47.0分。", "confidence": "computed", "trace": {}, "evidence_chain": []}],
                "numeric_rows": [["avg_score", "47.0", "分", "综合均分"]],
                "chart_data_uri": "data:image/png;base64,iVBORw0KGgo=",
            },
            {
                "title": "行业趋势",
                "purpose": "各行业营收同比",
                "claims": [{"claim": "制造行业同比 5%。", "confidence": "computed", "trace": {}, "evidence_chain": []}],
                "numeric_rows": [["avg_revenue_yoy", "5.2", "%", "制造同比"]],
                "chart_data_uri": None,
            },
        ],
        "attribution": {
            "summary": "全样本（193家）综合均分47.0分，税务违法拖累明显。",
            "drag_factors": [{"item": "税务违法", "count": 12}],
            "dimensions": {
                "tax_health": {"label": "税务健康", "score": 55, "weight": 0.25, "net_contribution": 13.75},
                "legal": {"label": "法律合规", "score": 70, "weight": 0.05, "net_contribution": 3.5},
            },
        },
        "attribution_chart_data_uri": "data:image/png;base64,iVBORw0KGgo=",
        "summary_conclusion": "综合均分 47.0 分，风险等级「中高风险」，样本 193 家",
        "summary_strengths": ["「法律合规」维度均分 70.0 分（相对稳健）"],
        "summary_risks": ["税务违法（12 家）", "重点关注主体 3 家"],
        "validation": {"ok": True, "total_claims": 6, "unanchored": 0},
        "appendix": {
            "data": ["core_metrics", "syx_tax_illega", "syx_auditing"],
            "methods": ["趋势聚合", "Benford", "互斥分桶预警", "抗幻觉：仅保留 computed/inferred"],
        },
    }


REQUIRED_MARKERS = [
    "行业趋势风控报告",
    "风险控制报告",
    "样本规模",
    "执行摘要",
    "主要优势",
    "主要风险",
    "综合均分 47.0 分",
    "税务违法（12 家）",
    "重点关注主体 3 家",
    "六维雷达 · 综合画像",
    "维度归因",
    "主要拖累因素",
    "抗幻觉",
    "附录",
    "core_metrics",
]


def test_report_html_structure_snapshot(tmp_path):
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")
    ctx = _full_context()
    ctx.pop("attribution_chart_data_uri", None)
    ctx["attribution_chart"] = str(chart_path)
    ctx["chapters"][0].pop("chart_data_uri", None)
    ctx["chapters"][0]["chart_image"] = str(chart_path)
    html = build_report_html(ctx, "slice_general_structure_test")
    for marker in REQUIRED_MARKERS:
        assert marker in html, f"missing section marker: {marker}"
    assert "data:image/png;base64," in html
    assert html.count("<table") >= 2


def test_cover_serious_style():
    """封面严肃化：藏蓝满版 + 品牌 + 场景副标题 + 密级；无母题 SVG/无营销芯片/无校验徽章。"""
    ctx = _full_context()
    ctx["scenario"] = "financial"
    ctx["cover"] = {"motif": "ledger", "accent": "#0f766e"}
    ctx["subtitle"] = "盈利能力 · 偿债能力 · 营运能力 · 现金流"
    ctx["data_focus"] = ["财务数据", "企业基础信息"]
    html = build_report_html(ctx, "slice_financial_cover_test")
    assert "#0f766e" in html            # 主色仍作 in-page 强调色（:root --accent）
    assert "盈利能力" in html            # 副标题 → 封面 scope 行
    assert "风险控制报告" in html          # 封面类别
    assert "机密" in html               # 密级提示
    assert "<rect" not in html          # 不再渲染母题 SVG 图标
    assert "抗幻觉校验" not in html        # 校验徽章不上封面


def test_design_tokens_centralized_slice():
    """L4 设计令牌：切片模板共用 _brand_tokens.css，正文用 var() 引用。"""
    html = build_report_html(_full_context(), "slice_tokens_test")
    assert "--brand: #003366" in html   # 令牌定义（含品牌藏蓝）
    assert "var(--brand)" in html
    assert "var(--ink)" in html
    assert "var(--accent)" in html
    assert "--font-sans" in html


def _enterprise_context():
    return {
        "scenario": "enterprise",
        "scenario_label": "企业财务分析报告",
        "tier": "general",
        "title": "企业财务分析报告 · #abc12345",
        "story": "针对匿名样本的财务深度分析。",
        "report_date": "2026年08月27日",
        "subject": {
            "short_id": "abc12345", "label": "样本", "industry_l1": "制造",
            "industry_l2": "通用设备", "province": "广东", "report_year": "2024",
        },
        "overall": {
            "health": "良好", "health_color": "#2e7d32", "risk_level": "低风险",
            "overall_score": 72.5, "reason": "综合评分72.5分，风险等级低风险。",
            "risk_points": ["毛利率偏低"], "advantages": ["资产负债率达标"], "advice": ["关注成本结构"],
        },
        "dimensions": [
            {
                "title": "盈利风险", "risk_level": "低", "risk_color": "#2e7d32",
                "metrics": [{"label": "毛利率", "value": "23.5%", "unit": "", "standard": "≥20%", "rating": "达标"}],
                "analysis": {"level_review": "1项达标。", "trend": "单期无跨期比较。", "risks": "无预警。", "advice": "保持。"},
            }
        ],
        "statements": {
            "income": {"title": "利润表", "rows": [["营业收入", "1,000.00"]]},
            "balance": {"title": "资产负债表", "rows": [["资产总计", "2,000.00"]]},
            "cashflow": {"title": "现金流量表", "rows": [["经营活动现金流量净额", "100.00"]]},
        },
        "radar_chart": None,
        "validation": {"ok": True, "total_claims": 1, "unanchored": 0},
        "appendix": {"data": ["core_metrics"], "methods": ["六维加权评分"]},
    }


def test_design_tokens_centralized_enterprise():
    """L4 设计令牌：个体模板同样引用 _brand_tokens.css 的令牌。"""
    html = build_report_html(_enterprise_context(), "ent_tokens_test")
    assert "--brand: #003366" in html
    assert "var(--brand)" in html
    assert "var(--gold)" in html
