"""
Mock 数据服务 — 当 PostgreSQL 不可用时提供企业模拟数据
配合 LLM 生成真实回复，确保演示链路完整可用

标记：所有数据标注 source: "mock" 以便前端区分

注意：此文件的 ENT001-010 评分是手工编写的演示数据，
与 seed_data.py 的随机生成值不同。真实数据接入后两者均弃用。
"""

from __future__ import annotations

from typing import Any

# 10 家种子企业完整数据（对齐企划书 B 的 core_metrics schema）
MOCK_ENTERPRISES: list[dict[str, Any]] = [
    {
        "enterprise_id": "ENT001",
        "enterprise_name": "广东·制造业·小型",
        "industry_l1": "制造业",
        "industry_l2": "电子设备",
        "province": "广东",
        "city": "深圳",
        "credit_level": "A",
        "credit_score": 90.5,
        "tax_on_time_rate": 0.952,
        "tax_arrears_cnt": 0,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 2_800_000_000,
        "public_revenue": 2_650_000_000,
        "revenue_deviation": 0.0566,
        "invoice_monthly_avg": 1247,
        "social_trend": "增长",
        "market_cap": 45_000_000_000,
        "pe_ratio": 22.5,
        "revenue_yoy": 0.153,
        "profit_yoy": 0.182,
        "roe": 0.165,
        "debt_ratio": 0.42,
        "z_score": 3.8,
        "z_score_level": "安全",
        "overall_score": 85.2,
        "risk_level": "低风险",
        "dimensions": {
            "tax_health": 88,
            "authenticity": 82,
            "invoice": 75,
            "industry": 85,
            "legal": 90,
            "finance": 81,
        },
        "warning_signals": [],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT002",
        "enterprise_name": "上海·批发零售·小型",
        "industry_l1": "批发零售",
        "industry_l2": "进出口贸易",
        "province": "上海",
        "city": "上海",
        "credit_level": "B",
        "credit_score": 72.0,
        "tax_on_time_rate": 0.883,
        "tax_arrears_cnt": 1,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 1_200_000_000,
        "public_revenue": 1_350_000_000,
        "revenue_deviation": -0.111,
        "invoice_monthly_avg": 856,
        "social_trend": "稳定",
        "market_cap": 18_000_000_000,
        "pe_ratio": 15.8,
        "revenue_yoy": 0.082,
        "profit_yoy": 0.065,
        "roe": 0.098,
        "debt_ratio": 0.56,
        "z_score": 2.4,
        "z_score_level": "灰色",
        "overall_score": 68.5,
        "risk_level": "中低风险",
        "dimensions": {
            "tax_health": 70,
            "authenticity": 65,
            "invoice": 75,
            "industry": 68,
            "legal": 75,
            "finance": 64,
        },
        "warning_signals": ["发票月均大幅下降"],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT003",
        "enterprise_name": "北京·信息技术·中型",
        "industry_l1": "信息技术",
        "industry_l2": "软件服务",
        "province": "北京",
        "city": "北京",
        "credit_level": "A",
        "credit_score": 88.0,
        "tax_on_time_rate": 0.975,
        "tax_arrears_cnt": 0,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 3_500_000_000,
        "public_revenue": 3_400_000_000,
        "revenue_deviation": 0.0294,
        "invoice_monthly_avg": 2103,
        "social_trend": "增长",
        "market_cap": 120_000_000_000,
        "pe_ratio": 35.2,
        "revenue_yoy": 0.245,
        "profit_yoy": 0.281,
        "roe": 0.215,
        "debt_ratio": 0.28,
        "z_score": 5.2,
        "z_score_level": "安全",
        "overall_score": 91.8,
        "risk_level": "低风险",
        "dimensions": {
            "tax_health": 92,
            "authenticity": 90,
            "invoice": 75,
            "industry": 93,
            "legal": 95,
            "finance": 89,
        },
        "warning_signals": [],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT004",
        "enterprise_name": "广东·制造业·中型",
        "industry_l1": "制造业",
        "industry_l2": "机械设备",
        "province": "广东",
        "city": "广州",
        "credit_level": "B",
        "credit_score": 74.5,
        "tax_on_time_rate": 0.901,
        "tax_arrears_cnt": 0,
        "tax_violation_cnt": 1,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 4_200_000_000,
        "public_revenue": 4_000_000_000,
        "revenue_deviation": 0.050,
        "invoice_monthly_avg": 1890,
        "social_trend": "稳定",
        "market_cap": 32_000_000_000,
        "pe_ratio": 18.6,
        "revenue_yoy": 0.112,
        "profit_yoy": 0.095,
        "roe": 0.123,
        "debt_ratio": 0.51,
        "z_score": 2.8,
        "z_score_level": "灰色",
        "overall_score": 72.3,
        "risk_level": "中低风险",
        "dimensions": {
            "tax_health": 75,
            "authenticity": 70,
            "invoice": 75,
            "industry": 72,
            "legal": 78,
            "finance": 68,
        },
        "warning_signals": ["营收偏差过高"],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT005",
        "enterprise_name": "浙江·新能源·小型",
        "industry_l1": "新能源",
        "industry_l2": "光伏组件",
        "province": "浙江",
        "city": "杭州",
        "credit_level": "A",
        "credit_score": 86.0,
        "tax_on_time_rate": 0.938,
        "tax_arrears_cnt": 0,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 6_800_000_000,
        "public_revenue": 7_200_000_000,
        "revenue_deviation": -0.0556,
        "invoice_monthly_avg": 3200,
        "social_trend": "增长",
        "market_cap": 85_000_000_000,
        "pe_ratio": 28.4,
        "revenue_yoy": 0.352,
        "profit_yoy": 0.421,
        "roe": 0.188,
        "debt_ratio": 0.45,
        "z_score": 3.1,
        "z_score_level": "安全",
        "overall_score": 82.6,
        "risk_level": "低风险",
        "dimensions": {
            "tax_health": 84,
            "authenticity": 78,
            "invoice": 75,
            "industry": 88,
            "legal": 85,
            "finance": 78,
        },
        "warning_signals": [],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT006",
        "enterprise_name": "四川·交通运输·小型",
        "industry_l1": "交通运输",
        "industry_l2": "供应链物流",
        "province": "四川",
        "city": "成都",
        "credit_level": "C",
        "credit_score": 58.0,
        "tax_on_time_rate": 0.724,
        "tax_arrears_cnt": 3,
        "tax_violation_cnt": 1,
        "high_severity_cnt": 1,
        "is_dishonesty": False,
        "is_execution": True,
        "vat_revenue": 850_000_000,
        "public_revenue": 920_000_000,
        "revenue_deviation": -0.0761,
        "invoice_monthly_avg": 420,
        "social_trend": "缩减",
        "market_cap": 5_200_000_000,
        "pe_ratio": 12.1,
        "revenue_yoy": -0.035,
        "profit_yoy": -0.128,
        "roe": 0.032,
        "debt_ratio": 0.72,
        "z_score": 1.4,
        "z_score_level": "困境",
        "overall_score": 41.5,
        "risk_level": "中高风险",
        "dimensions": {
            "tax_health": 42,
            "authenticity": 38,
            "invoice": 75,
            "industry": 45,
            "legal": 35,
            "finance": 48,
        },
        "warning_signals": ["信用降级", "社保缩减", "涉诉风险", "发票骤降"],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT007",
        "enterprise_name": "湖北·医药·小微",
        "industry_l1": "医药",
        "industry_l2": "生物制药",
        "province": "湖北",
        "city": "武汉",
        "credit_level": "B",
        "credit_score": 76.0,
        "tax_on_time_rate": 0.915,
        "tax_arrears_cnt": 0,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 1_500_000_000,
        "public_revenue": 1_450_000_000,
        "revenue_deviation": 0.0345,
        "invoice_monthly_avg": 980,
        "social_trend": "增长",
        "market_cap": 28_000_000_000,
        "pe_ratio": 42.5,
        "revenue_yoy": 0.195,
        "profit_yoy": 0.225,
        "roe": 0.142,
        "debt_ratio": 0.33,
        "z_score": 3.5,
        "z_score_level": "安全",
        "overall_score": 76.9,
        "risk_level": "中低风险",
        "dimensions": {
            "tax_health": 80,
            "authenticity": 75,
            "invoice": 75,
            "industry": 78,
            "legal": 82,
            "finance": 72,
        },
        "warning_signals": [],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT008",
        "enterprise_name": "江苏·建筑业·小型",
        "industry_l1": "建筑业",
        "industry_l2": "工程建设",
        "province": "江苏",
        "city": "南京",
        "credit_level": "B",
        "credit_score": 70.5,
        "tax_on_time_rate": 0.856,
        "tax_arrears_cnt": 1,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 2_100_000_000,
        "public_revenue": 1_950_000_000,
        "revenue_deviation": 0.0769,
        "invoice_monthly_avg": 670,
        "social_trend": "稳定",
        "market_cap": 12_000_000_000,
        "pe_ratio": 9.8,
        "revenue_yoy": 0.065,
        "profit_yoy": 0.042,
        "roe": 0.075,
        "debt_ratio": 0.68,
        "z_score": 1.8,
        "z_score_level": "困境",
        "overall_score": 58.2,
        "risk_level": "中等风险",
        "dimensions": {
            "tax_health": 62,
            "authenticity": 55,
            "invoice": 75,
            "industry": 58,
            "legal": 65,
            "finance": 52,
        },
        "warning_signals": ["负债偏高", "Z值预警"],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT009",
        "enterprise_name": "天津·交通运输·中型",
        "industry_l1": "交通运输",
        "industry_l2": "港口服务",
        "province": "天津",
        "city": "天津",
        "credit_level": "C",
        "credit_score": 55.0,
        "tax_on_time_rate": 0.698,
        "tax_arrears_cnt": 2,
        "tax_violation_cnt": 2,
        "high_severity_cnt": 1,
        "is_dishonesty": False,
        "is_execution": True,
        "vat_revenue": 620_000_000,
        "public_revenue": 580_000_000,
        "revenue_deviation": 0.0690,
        "invoice_monthly_avg": 285,
        "social_trend": "缩减",
        "market_cap": 3_800_000_000,
        "pe_ratio": 8.2,
        "revenue_yoy": -0.082,
        "profit_yoy": -0.195,
        "roe": 0.018,
        "debt_ratio": 0.75,
        "z_score": 1.1,
        "z_score_level": "困境",
        "overall_score": 35.8,
        "risk_level": "高风险",
        "dimensions": {
            "tax_health": 35,
            "authenticity": 32,
            "invoice": 75,
            "industry": 38,
            "legal": 28,
            "finance": 45,
        },
        "warning_signals": ["信用降级", "纳税准时率低", "社保缩减", "涉诉风险", "报表偏差"],
        "source": "mock",
    },
    {
        "enterprise_id": "ENT010",
        "enterprise_name": "重庆·餐饮·小型",
        "industry_l1": "餐饮",
        "industry_l2": "连锁餐饮",
        "province": "重庆",
        "city": "重庆",
        "credit_level": "C",
        "credit_score": 62.0,
        "tax_on_time_rate": 0.782,
        "tax_arrears_cnt": 1,
        "tax_violation_cnt": 0,
        "high_severity_cnt": 0,
        "is_dishonesty": False,
        "is_execution": False,
        "vat_revenue": 380_000_000,
        "public_revenue": 420_000_000,
        "revenue_deviation": -0.0952,
        "invoice_monthly_avg": 520,
        "social_trend": "稳定",
        "market_cap": 2_100_000_000,
        "pe_ratio": 18.5,
        "revenue_yoy": 0.045,
        "profit_yoy": -0.022,
        "roe": 0.055,
        "debt_ratio": 0.62,
        "z_score": 1.6,
        "z_score_level": "困境",
        "overall_score": 48.7,
        "risk_level": "中等风险",
        "dimensions": {
            "tax_health": 52,
            "authenticity": 48,
            "invoice": 75,
            "industry": 45,
            "legal": 55,
            "finance": 44,
        },
        "warning_signals": ["信用降级", "发票骤降"],
        "source": "mock",
    },
]

MOCK_LEGAL_EVENTS: dict[str, list[dict[str, Any]]] = {
    "ENT006": [
        {"id": 1, "enterprise_id": "ENT006", "event_type": "execution", "severity": "H", "amount_involved": 12_000_000, "event_date": "2025-08-15", "description": "因合同纠纷被执行，涉案金额1200万元", "source": "执行网"},
        {"id": 2, "enterprise_id": "ENT006", "event_type": "tax_violation", "severity": "M", "amount_involved": 500_000, "event_date": "2025-03-22", "description": "税务行政处罚：少缴税款50万元", "source": "税务数据"},
        {"id": 3, "enterprise_id": "ENT006", "event_type": "civil_lawsuit", "severity": "L", "amount_involved": 200_000, "event_date": "2025-06-10", "description": "民事诉讼被告：货物运输合同纠纷", "source": "企查查"},
    ],
    "ENT008": [
        {"id": 4, "enterprise_id": "ENT008", "event_type": "civil_lawsuit", "severity": "M", "amount_involved": 3_500_000, "event_date": "2025-05-08", "description": "工程款纠纷，被诉支付拖欠工程款350万元", "source": "企查查"},
    ],
    "ENT009": [
        {"id": 5, "enterprise_id": "ENT009", "event_type": "execution", "severity": "H", "amount_involved": 25_000_000, "event_date": "2025-02-14", "description": "因金融借款合同纠纷被执行，涉案金额2500万元", "source": "执行网"},
        {"id": 6, "enterprise_id": "ENT009", "event_type": "tax_arrears", "severity": "M", "amount_involved": 1_800_000, "event_date": "2025-01-20", "description": "欠缴税款180万元", "source": "税务数据"},
        {"id": 7, "enterprise_id": "ENT009", "event_type": "admin_penalty", "severity": "L", "amount_involved": 80_000, "event_date": "2025-04-05", "description": "港口作业安全违规行政处罚", "source": "企查查"},
    ],
    "ENT010": [
        {"id": 8, "enterprise_id": "ENT010", "event_type": "civil_lawsuit", "severity": "L", "amount_involved": 150_000, "event_date": "2025-07-01", "description": "食品质量纠纷民事诉讼", "source": "企查查"},
    ],
}


def _anon_display_label(ent: dict[str, Any]) -> str:
    prov = ent.get("province") or "未知"
    l1 = ent.get("industry_l1") or "其他"
    rev = float(ent.get("vat_revenue") or ent.get("invoice_monthly_avg") or 0)
    if rev >= 3_000_000_000:
        scale = "中型"
    elif rev >= 500_000_000:
        scale = "小型"
    else:
        scale = "小微"
    return f"{prov}·{l1}·{scale}"


def _normalize_mock_ent(ent: dict[str, Any]) -> dict[str, Any]:
    out = dict(ent)
    label = _anon_display_label(out)
    out["display_label"] = label
    out["enterprise_name"] = label  # API 兼容字段 = 匿名标签
    return out


for _i, _ent in enumerate(MOCK_ENTERPRISES):
    MOCK_ENTERPRISES[_i] = _normalize_mock_ent(_ent)


def get_mock_enterprise(enterprise_id: str) -> dict[str, Any] | None:
    """根据 ID 获取单个企业 mock 数据。10 家种子企业有完整数据，其余返回占位数据。"""
    for ent in MOCK_ENTERPRISES:
        if ent["enterprise_id"] == enterprise_id:
            return dict(ent)
    # ENT011+ 占位：真实数据导入后替换
    if enterprise_id.startswith("ENT") and len(enterprise_id) == 6:
        num = int(enterprise_id[3:])
        if 11 <= num <= 200:
            return {
                "enterprise_id": enterprise_id,
                "display_label": f"样本·占位·{enterprise_id}",
                "enterprise_name": f"样本·占位·{enterprise_id}",
                "overall_score": 50,
                "risk_level": "中等风险",
                "credit_level": "B",
                "dimensions": {"tax_health": 50, "authenticity": 50, "invoice": 50, "industry": 50, "legal": 50, "finance": 50},
                "warning_signals": [],
                "source": "mock_placeholder",
            }
    return None


def get_mock_enterprise_by_name(name: str) -> dict[str, Any] | None:
    """匿名模式：不再按具名企业匹配。"""
    return None


def get_all_mock_enterprises() -> list[dict[str, Any]]:
    """获取全部 mock 企业列表（仅基础字段）"""
    return [
        {
            "enterprise_id": e["enterprise_id"],
            "enterprise_name": e["enterprise_name"],
            "overall_score": e["overall_score"],
            "risk_level": e["risk_level"],
            "credit_level": e["credit_level"],
            "dimensions": e["dimensions"],
            "warning_signals": e["warning_signals"],
            "source": "mock",
        }
        for e in MOCK_ENTERPRISES
    ]


def get_mock_legal_events(enterprise_id: str) -> list[dict[str, Any]]:
    """获取企业的 mock 法律事件"""
    return MOCK_LEGAL_EVENTS.get(enterprise_id, [])


def get_mock_warnings() -> list[dict[str, Any]]:
    """获取所有有预警信号的企业"""
    return [
        {
            "enterprise_id": e["enterprise_id"],
            "display_label": e.get("display_label") or e["enterprise_name"],
            "enterprise_name": e.get("display_label") or e["enterprise_name"],
            "industry_l1": e.get("industry_l1"),
            "overall_score": e["overall_score"],
            "risk_level": e["risk_level"],
            "warning_signals": e["warning_signals"],
            "source": "mock",
        }
        for e in MOCK_ENTERPRISES
        if e["warning_signals"]
    ]


def _to_frontend_enterprise(ent: dict[str, Any]) -> dict[str, Any]:
    """前端 EnterpriseAssessment 字段形状。"""
    label = ent.get("display_label") or ent["enterprise_name"]
    return {
        "enterprise_id": ent["enterprise_id"],
        "enterprise_name": label,
        "display_label": label,
        "credit_level": ent.get("credit_level", "B"),
        "tax_on_time_rate": float(ent.get("tax_on_time_rate") or 0),
        "invoice_monthly_avg": int(ent.get("invoice_monthly_avg") or 0),
        "revenue_deviation": float(ent.get("revenue_deviation") or 0),
        "social_trend": ent.get("social_trend") or "稳定",
        "industry_l1": ent.get("industry_l1"),
        "industry_l2": ent.get("industry_l2"),
        "province": ent.get("province"),
        "city": ent.get("city"),
        "overall_score": float(ent["overall_score"]),
        "risk_level": ent["risk_level"],
        "dimensions": dict(ent.get("dimensions") or {}),
        "dimension_details": {},
        "warning_signals": list(ent.get("warning_signals") or []),
        "source": "mock",
    }


def get_mock_dashboard_summary() -> dict[str, Any]:
    """工作台 KPI（mock 口径，与 MOCK_ENTERPRISES 一致）。"""
    dist: dict[str, int] = {}
    scores: list[float] = []
    high_risk = 0
    for e in MOCK_ENTERPRISES:
        rl = e["risk_level"]
        dist[rl] = dist.get(rl, 0) + 1
        scores.append(float(e["overall_score"]))
        if "高" in rl:
            high_risk += 1
    warnings = get_mock_warnings()
    avg = round(sum(scores) / len(scores), 1) if scores else 0.0
    return {
        "sample_count": len(MOCK_ENTERPRISES),
        "high_risk_count": high_risk,
        "avg_score": avg,
        "warning_count": len(warnings),
        "risk_distribution": dist,
        "enterprises": [
            {
                "enterprise_id": e["enterprise_id"],
                "display_label": e.get("display_label") or e["enterprise_name"],
                "risk_level": e["risk_level"],
                "overall_score": e["overall_score"],
                "industry_l1": e.get("industry_l1"),
            }
            for e in MOCK_ENTERPRISES
        ],
        "source": "mock",
    }


def get_mock_sample_bundle() -> dict[str, Any]:
    """前端 mock 单一路径：企业列表 + 预警 + 汇总。"""
    summary = get_mock_dashboard_summary()
    return {
        "enterprises": [_to_frontend_enterprise(e) for e in MOCK_ENTERPRISES],
        "warnings": get_mock_warnings(),
        "summary": summary,
        "source": "mock",
    }


def is_using_mock_data() -> bool:
    """已废弃：请使用 GET /api/v1/health 的 data_mode。"""
    return False
