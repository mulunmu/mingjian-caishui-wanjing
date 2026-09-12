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
            {"label": "综合经营表现", "value": "偏弱", "unit": ""},
            {"label": "关注行业", "value": "制造", "unit": ""},
        ],
        "chapters": [
            {
                "title": "六维雷达 · 综合画像",
                "purpose": "样本六个维度经营表现雷达画像",
                "claims": [{"claim": "全样本综合经营表现偏弱。", "confidence": "computed", "trace": {}, "evidence_chain": []}],
                "numeric_rows": [["avg_score", "偏弱", "", "综合经营表现"]],
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
            "summary": "全样本（193家）综合经营表现偏弱，税务违法拖累明显。",
            "drag_factors": [{"item": "税务违法", "count": 12}],
            "dimensions": {
                "tax_health": {"label": "税务健康", "score": 55, "weight": 0.25, "net_contribution": 13.75},
                "legal": {"label": "法律合规", "score": 70, "weight": 0.05, "net_contribution": 3.5},
            },
        },
        "attribution_chart_data_uri": "data:image/png;base64,iVBORw0KGgo=",
        "summary_conclusion": "群体风险判断「中高风险」，样本 193 家",
        "summary_strengths": ["「法律合规」维度表现稳健"],
        "summary_risks": ["税务违法（12 家）", "重点关注主体 3 家"],
        "validation": {"ok": True, "total_claims": 6, "unanchored": 0},
        "appendix": {
            "data": ["core_metrics", "syx_tax_illega", "syx_auditing"],
            "methods": ["趋势聚合", "互斥分桶预警", "抗幻觉：仅保留 computed/inferred"],
        },
    }


REQUIRED_MARKERS = [
    "行业趋势风控报告",
    "明鉴 · 财税票 · 万景",
    "样本规模",
    "执行摘要",
    "主要优势",
    "主要风险",
    "综合经营表现",
    "税务违法（12 家）",
    "重点关注主体 3 家",
    "六维雷达 · 综合画像",
    "维度归因",
    "主要拖累因素",
    "核心要点提炼",
    "【经营信号】",
    "【风险预警点】",
]

from app.services.report_templates import FORBIDDEN_MARKERS

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
    for marker in FORBIDDEN_MARKERS:
        assert marker not in html, f"forbidden marker leaked into report body: {marker}"
    assert "data:image/png;base64," in html
    assert html.count("<table") >= 2


def test_cover_serious_style():
    """封面统一：仅系统名 + 报告名 + 时间；不放风险等级/展望/表现。"""
    ctx = _full_context()
    ctx["scenario"] = "portrait"
    ctx["cover"] = {"motif": "badge", "accent": "#6d28d9"}
    ctx["subtitle"] = "结构分布 · 均值分布"
    ctx["data_focus"] = ["企业基础信息"]
    html = build_report_html(ctx, "slice_portrait_cover_test")
    assert "明鉴" in html
    assert "报告日期" in html or "报告编号" in html
    cover_part = html.split("执行摘要")[0] if "执行摘要" in html else html
    assert "报告场景" not in cover_part
    assert "群体风险判断" not in cover_part
    assert "评级展望" not in cover_part
    assert "风险控制报告" not in html
    assert "<rect" not in html          # 不再渲染母题 SVG 图标
    assert "抗幻觉校验" not in html        # 校验徽章不上封面


def test_slice_kpi_empty_card_skipped():
    """KPI 值为「—」（弃权）→ 卡片不渲染（空数据消除）。"""
    ctx = _full_context()
    ctx["summary_kpis"] = [
        {"label": "样本规模", "value": "193", "unit": "家"},
        {"label": "关注行业", "value": "—", "unit": ""},
    ]
    html = build_report_html(ctx, "slice_kpi_empty_test")
    assert "样本规模" in html
    assert "关注行业" not in html  # 「—」卡整体不出现


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
        "title": "企业财务分析报告 · 企业1",
        "story": "针对脱敏样本的财务深度分析。",
        "report_date": "2026年08月27日",
        "subject": {
            "short_id": "abc12345", "label": "样本", "industry_l1": "制造",
            "industry_l2": "通用设备", "province": "广东", "report_year": "2024",
        },
        "overall": {
            "health": "良好", "health_color": "#2e7d32", "risk_level": "低风险",
            "overall_score": 72.5, "reason": "综合风险等级低风险。",
            "hit_risk_count": 1, "checked_metric_count": 8,
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
        "appendix": {"data": ["core_metrics"], "methods": ["六维经营表现"]},
    }


def test_design_tokens_centralized_enterprise():
    """L4 设计令牌：个体模板同样引用 _brand_tokens.css 的令牌。"""
    html = build_report_html(_enterprise_context(), "ent_tokens_test")
    assert "--brand: #003366" in html
    assert "var(--brand)" in html
    assert "var(--gold)" in html


def test_enterprise_subject_meta_drops_empty():
    """空数据消除：无财务报表时 report_year/industry/province 为 None → 元数据行不渲染（无「—」）。"""
    ctx = _enterprise_context()
    ctx["subject"]["report_year"] = None
    ctx["subject"]["industry_l1"] = None
    ctx["subject"]["industry_l2"] = None
    ctx["subject"]["province"] = None
    html = build_report_html(ctx, "ent_subject_empty_test")
    assert "报告年度" not in html
    assert "所属行业" not in html
    assert "所属地区" not in html
    assert "None" not in html


def test_dimension_analysis_expert_voice():
    """维度解读：结论前置（承压/越线/需优先核查），不再用「该维度 X 项评级指标中…」学术句式。"""
    from app.services.slice_report import _dimension_analysis

    metrics = [
        {"label": "流动比率", "value": "0.9", "unit": "", "standard": "≥1.0", "rating": "预警"},
        {"label": "速动比率", "value": "0.4", "unit": "", "standard": "≥0.5", "rating": "预警"},
    ]
    out = _dimension_analysis("solvency", metrics, warn=2, passed=0, risk="高", total=2)
    assert "项评级指标" not in out["level_review"]
    assert "该维度" not in out["level_review"]
    assert "越线" in out["level_review"]
    assert "需优先核查" in out["level_review"]
    assert out["risks"]  # 越线依据存在
    assert out["advice"]  # 有预警 → 才给处置建议（claim 唯一化：建议绑定预警条件）

    ok_metrics = [{"label": "流动比率", "value": "1.5", "unit": "", "standard": "≥1.0", "rating": "达标"}]
    ok = _dimension_analysis("solvency", ok_metrics, warn=0, passed=1, risk="低", total=1)
    assert "均达标" in ok["level_review"]
    assert ok["risks"] == ""  # 无预警 → 不硬凑风险点
    assert ok["advice"] == ""  # 达标 → 不输出风险建议（防「达标出风险话术」矛盾）


def test_radar_interpretation_expert_voice():
    """雷达解读：点最弱维度为主要风险来源、最稳健维度为优势；无有效维度则弃权。"""
    from app.services.slice_report import _radar_interpretation

    profile = {"dimensions": {
        "tax_health": 82.0, "authenticity": 60.0, "invoice": 45.0,
        "industry": 70.0, "legal": 90.0, "finance": 55.0,
    }}
    text = _radar_interpretation(profile)
    assert "主要风险来源" in text
    assert "相对稳健" in text
    assert _radar_interpretation({"dimensions": {"tax_health": 0.0, "authenticity": 0.0}}) == ""


def test_radar_dimensions_for_chapters_alignment():
    """雷达 ⊆ 章节（铁律）：无对应章节的维度（如法律合规）不进入雷达。"""
    from app.services.report_templates import radar_dimensions_for_chapters

    due_diligence = [
        {"function": "score", "dimension": "industry"},
        {"function": "authenticity", "dimension": "overall"},
        {"function": "fraud", "dimension": "overall"},
        {"function": "benchmark", "dimension": "industry"},
        {"function": "signal", "dimension": "signal"},
    ]
    dims = radar_dimensions_for_chapters(due_diligence)
    # 综合尽调无法律合规章节 → 法律合规不得出现在雷达
    assert "legal" not in dims
    assert "tax_health" in dims and "finance" in dims and "invoice" in dims

    financial_only = [{"function": "financial", "dimension": "overall"}]
    assert radar_dimensions_for_chapters(financial_only) == ["finance"]

    overview = [{"function": "score", "dimension": "overall"}]
    assert len(radar_dimensions_for_chapters(overview)) == 6  # overall 归因覆盖全六维


def test_benchmark_interpretation_expert_voice():
    """同业对标解读：结论前置「弱于/优于同业」并挂本样本 vs 行业数值；无基准则弃权。"""
    from types import SimpleNamespace

    from app.services.slice_report import _benchmark_interpretation

    fin = SimpleNamespace(debt_ratio=0.78, gross_margin=0.12, net_margin=0.06, roe=0.15, roa=0.05)
    bench = SimpleNamespace(
        avg_debt_ratio=0.55, avg_gross_margin=0.18, avg_net_margin=0.04,
        avg_roe=0.08, avg_roa=0.04,
    )
    text = _benchmark_interpretation(fin, True, bench)
    assert "弱于同业" in text
    assert "优于同业" in text
    assert "%" in text  # 数值为 L0 百分比，非新造
    assert _benchmark_interpretation(fin, False, bench) == ""
    assert _benchmark_interpretation(fin, True, None) == ""


def test_zh_report_title_chinese_filename():
    """下载文件名兜底：slice/ent 报告 id 反解中文标题，未知 id 回退「评估报告」。"""
    from app.services.report_templates import zh_report_title

    assert zh_report_title("slice_portrait_20260827_120000_ab12cd34") == "样本库画像报告"
    assert zh_report_title("slice_alert_20260827_120000_ab12cd34") == "风险预警报告"
    # 旧 key 仍能反解（别名标题已统一为预警/画像）
    assert zh_report_title("slice_financial_20260827_120000_ab12cd34") == "风险预警报告"
    assert zh_report_title("ent_a1b2c3d4_20260827_120000_ab12cd34") == "企业风险披露报告"
    assert zh_report_title("slice_unknown_20260827_120000_ab12cd34") == "评估报告"


def test_safe_filename_strips_illegal_chars():
    """下载文件名清洗：去除 Windows/Unix 非法字符，保留中文标题。"""
    from app.api.v1.report import _safe_filename

    assert _safe_filename('广东省 · 财务健康体检报告') == '广东省 · 财务健康体检报告'
    assert _safe_filename('a/b\\c:d*e?f"g<h>i|j') == 'abcdefghij'
    assert _safe_filename('') == '评估报告'
