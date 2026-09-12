"""指标语义层：规范口径字典（seed + 导出）。

口径字典是报告可信的地基——同一指标无论谁问、怎么问，口径一致（见 PRINCIPLES.md）。
本模块沉淀 10 个规范指标，公式对齐 assessment.py 实际计算逻辑，源字段对齐 core_metrics 列。
JSON 字段沿用 Text 存储，读写处 json.dumps/loads。

参考：dbt MetricFlow（metric type / grain / dimensions / filters）、querychat（数据字典作 LLM 上下文）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# 目标源字段词汇表（供字典导出 + 四层字段映射引擎共用）。
# field 必须与 core_metrics 列名一致，category 对应六维 + 身份。
SOURCE_FIELDS: list[dict] = [
    # 身份
    {"field": "industry_l1", "description": "行业大类", "unit": "", "category": "identity"},
    {"field": "industry_l2", "description": "行业细类", "unit": "", "category": "identity"},
    {"field": "province", "description": "省份", "unit": "", "category": "identity"},
    {"field": "city", "description": "城市", "unit": "", "category": "identity"},
    {"field": "scale_label", "description": "企业规模标签（小微/中型/大型）", "unit": "", "category": "identity"},
    # 税务健康
    {"field": "credit_score", "description": "纳税信用分", "unit": "分", "category": "tax_health"},
    {"field": "tax_on_time_rate", "description": "纳税准时率", "unit": "", "category": "tax_health"},
    {"field": "tax_arrears_cnt", "description": "欠税记录条数", "unit": "条", "category": "tax_health"},
    {"field": "tax_violation_cnt", "description": "税务违法次数", "unit": "次", "category": "tax_health"},
    {"field": "high_severity_cnt", "description": "高危事件次数", "unit": "次", "category": "tax_health"},
    {"field": "is_dishonesty", "description": "是否失信", "unit": "", "category": "tax_health"},
    {"field": "is_execution", "description": "是否被执行", "unit": "", "category": "tax_health"},
    {"field": "vat_burden", "description": "增值税税负率", "unit": "%", "category": "tax_health"},
    {"field": "income_tax_burden", "description": "所得税税负率", "unit": "%", "category": "tax_health"},
    {"field": "correction_times", "description": "申报更正次数", "unit": "次", "category": "tax_health"},
    {"field": "social_headcount", "description": "社保缴费人数（最新）", "unit": "人", "category": "tax_health"},
    {"field": "tax_late_penalty_cnt", "description": "滞纳金/罚款笔数", "unit": "笔", "category": "tax_health"},
    {"field": "change_cnt", "description": "变更登记次数", "unit": "次", "category": "tax_health"},
    # 真实性 / 发票
    {"field": "vat_revenue", "description": "增值税口径营收", "unit": "元", "category": "authenticity"},
    {"field": "invoice_revenue", "description": "发票口径营收", "unit": "元", "category": "authenticity"},
    {"field": "finance_revenue", "description": "财务口径营收", "unit": "元", "category": "authenticity"},
    {"field": "revenue_deviation", "description": "营收口径偏差（三口径离散度）", "unit": "", "category": "authenticity"},
    {"field": "invoice_monthly_avg", "description": "月均开票张数", "unit": "张", "category": "authenticity"},
    {"field": "invoice_cnt", "description": "开票张数", "unit": "张", "category": "authenticity"},
    {"field": "red_invoice_cnt", "description": "红字发票张数", "unit": "张", "category": "authenticity"},
    {"field": "customer_concentration", "description": "客户 TOP1 金额占比", "unit": "%", "category": "invoice"},
    {"field": "supplier_concentration", "description": "供应商 TOP1 金额占比", "unit": "%", "category": "invoice"},
    {"field": "category_concentration", "description": "品目 TOP1 金额占比", "unit": "%", "category": "invoice"},
    {"field": "void_invoice_cnt", "description": "作废发票笔数", "unit": "笔", "category": "invoice"},
    {"field": "unit_price_ratio", "description": "最高单价/均价（单价离散度）", "unit": "倍", "category": "invoice"},
    # 财务
    {"field": "profit_margin", "description": "利润率", "unit": "", "category": "finance"},
    {"field": "revenue_yoy", "description": "营收同比", "unit": "", "category": "finance"},
    {"field": "profit_yoy", "description": "利润同比", "unit": "", "category": "finance"},
    {"field": "debt_ratio", "description": "资产负债率", "unit": "", "category": "finance"},
    {"field": "cash_flow_net", "description": "净现金流", "unit": "元", "category": "finance"},
    {"field": "cash_flow_level", "description": "现金流水平标签", "unit": "", "category": "finance"},
]

# 规范指标：key 与 slice_report._numeric_table_rows 的 metric 名、assessment 维度名对齐。
CANONICAL_METRICS: list[dict] = [
    {
        "metric_key": "overall_score",
        "name": "综合风险得分",
        "description": "六维加权综合得分，衡量主体综合风险水平。",
        "metric_type": "derived",
        "formula": "0.20*tax_health + 0.20*authenticity + 0.15*invoice + 0.15*industry + 0.15*legal + 0.15*finance",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": [],
        "dimensions": ["industry_l1", "province", "scale_label", "time"],
        "default_filters": {},
        "edge_cases": "六维权重见 assessment_weights.DIMENSION_WEIGHTS；法律维度缺事件时按部分覆盖权重 0.05 折算。",
    },
    {
        "metric_key": "tax_health_score",
        "name": "税务健康得分",
        "description": "基于纳税信用、准时率与欠税/违法/失信等负面事件的健康度得分。",
        "metric_type": "computed",
        "formula": "0.4*credit_score + 0.3*tax_on_time_rate*100 - 10*tax_arrears_cnt - 15*tax_violation_cnt - 5*min(high_severity,tax_violation) - 20*max(0,high_severity-tax_violation) - 25*is_dishonesty - 25*is_execution（高危为违法子集，禁止 15+20 全额双扣）",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": [
            "credit_score", "tax_on_time_rate", "tax_arrears_cnt",
            "tax_violation_cnt", "high_severity_cnt", "is_dishonesty", "is_execution",
        ],
        "dimensions": ["industry_l1", "province", "scale_label", "time"],
        "default_filters": {},
        "edge_cases": "得分下限 -50；tax_on_time_rate=0 为弃权哨兵，不计准时率贡献（与洞察 T-04 对齐，见 assessment._calc_tax_health）。",
    },
    {
        "metric_key": "authenticity_score",
        "name": "真实性得分",
        "description": "增值税/发票/财务三口径营收交叉验证与开票行为异常的综合真实性得分。",
        "metric_type": "computed",
        "formula": "交叉验证得分 + 口径一致加分（见 authenticity_engine.analyze_authenticity_from_metrics）",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": [
            "vat_revenue", "invoice_revenue", "finance_revenue", "revenue_deviation",
            "invoice_cnt", "red_invoice_cnt", "invoice_monthly_avg",
        ],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "红字发票、进销项不匹配、开票序列断档均为负向信号。",
    },
    {
        "metric_key": "industry_score",
        "name": "行业地位得分",
        "description": "相对同行业基准的营收/利润率分位表现。",
        "metric_type": "computed",
        "formula": "相对 industry_benchmark 的分位（revenue_yoy / profit_margin 等）",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": ["industry_l1", "revenue_yoy", "profit_margin"],
        "dimensions": ["industry_l1", "time"],
        "default_filters": {},
        "edge_cases": "非上市/其他行业无基准时退化为中性分。",
    },
    {
        "metric_key": "legal_score",
        "name": "法律合规得分",
        "description": "税务违法、失信、被执行等法律事件扣分后的合规得分。",
        "metric_type": "computed",
        "formula": "100 - Σ(事件扣分)；扣分见 assessment.EVENT_DEDUCTIONS",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": [
            "tax_violation_cnt", "high_severity_cnt", "is_dishonesty", "is_execution",
        ],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "事件缺失按部分覆盖权重 0.05 折算（LEGAL_PARTIAL_COVERAGE_WEIGHT）。",
    },
    {
        "metric_key": "finance_score",
        "name": "财务健康得分",
        "description": "利润率、同比、负债率、现金流综合的财务健康度得分。",
        "metric_type": "computed",
        "formula": "利润率/同比/负债/现金流分项合成",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": [
            "profit_margin", "revenue_yoy", "profit_yoy", "debt_ratio", "cash_flow_net", "cash_flow_level",
        ],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "非上市口径：无 ROE/Z 值，用利润边际与现金流水平替代。",
    },
    {
        "metric_key": "invoice_score",
        "name": "发票健康得分",
        "description": "进销/品目分散度分位与作废、单价异常扣分合成的发票健康度。",
        "metric_type": "computed",
        "formula": "分散度分位加权 - 作废/单价扣分（见 assessment._calc_invoice）",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": [
            "customer_concentration", "supplier_concentration", "category_concentration",
            "void_invoice_cnt", "unit_price_ratio", "invoice_cnt",
        ],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "集中度 0=弃权；三字段全弃权返回中性分 50。",
    },
    {
        "metric_key": "revenue_yoy",
        "name": "营收同比",
        "description": "营收较上年同期的增速。",
        "metric_type": "simple",
        "formula": "revenue_yoy",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["revenue_yoy"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "报告展示时 ×100 呈现百分比。",
    },
    {
        "metric_key": "credit_score",
        "name": "纳税信用分",
        "description": "税务信用评级量化分。",
        "metric_type": "simple",
        "formula": "credit_score",
        "unit": "分",
        "grain": "enterprise",
        "source_fields": ["credit_score"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "",
    },
    {
        "metric_key": "revenue_deviation",
        "name": "营收口径偏差",
        "description": "增值税/发票/财务三口径营收的离散度，越大越可疑。",
        "metric_type": "ratio",
        "formula": "discrepancy(vat_revenue, invoice_revenue, finance_revenue)",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["vat_revenue", "invoice_revenue", "finance_revenue"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "单一口径缺失时以可用口径计。",
    },
    {
        "metric_key": "profit_margin",
        "name": "利润率",
        "description": "净利润率（非上市口径）。",
        "metric_type": "simple",
        "formula": "profit_margin",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["profit_margin"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "",
    },
    {
        "metric_key": "customer_concentration",
        "name": "客户集中度",
        "description": "客户 TOP1 金额占比，越高客户越集中（0=弃权）。",
        "metric_type": "simple",
        "formula": "customer_concentration",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["customer_concentration"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "报告展示时 ×100 呈现百分比；0 表源缺失弃权。",
    },
    {
        "metric_key": "supplier_concentration",
        "name": "供应商集中度",
        "description": "供应商 TOP1 金额占比，越高供应商越集中（0=弃权）。",
        "metric_type": "simple",
        "formula": "supplier_concentration",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["supplier_concentration"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "报告展示时 ×100 呈现百分比；0 表源缺失弃权。",
    },
    {
        "metric_key": "category_concentration",
        "name": "品目集中度",
        "description": "品目 TOP1 金额占比，越高经营品类越单一（0=弃权）。",
        "metric_type": "simple",
        "formula": "category_concentration",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["category_concentration"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "报告展示时 ×100 呈现百分比；0 表源缺失弃权。",
    },
    {
        "metric_key": "vat_burden",
        "name": "增值税税负率",
        "description": "增值税税负率（0=弃权）。",
        "metric_type": "simple",
        "formula": "vat_burden",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["vat_burden"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "报告展示时 ×100 呈现百分比；0 表源缺失弃权。",
    },
    {
        "metric_key": "income_tax_burden",
        "name": "所得税税负率",
        "description": "所得税税负率（0=弃权）。",
        "metric_type": "simple",
        "formula": "income_tax_burden",
        "unit": "%",
        "grain": "enterprise",
        "source_fields": ["income_tax_burden"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "报告展示时 ×100 呈现百分比；0 表源缺失弃权。",
    },
    {
        "metric_key": "correction_times",
        "name": "申报更正次数",
        "description": "纳税申报更正次数，越高申报诚信越弱。",
        "metric_type": "simple",
        "formula": "correction_times",
        "unit": "次",
        "grain": "enterprise",
        "source_fields": ["correction_times"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "",
    },
    {
        "metric_key": "social_headcount",
        "name": "社保缴费人数",
        "description": "最新社保缴费人数（0 可能表源缺失弃权）。",
        "metric_type": "simple",
        "formula": "social_headcount",
        "unit": "人",
        "grain": "enterprise",
        "source_fields": ["social_headcount"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "0 表弃权，仅展示/问答不评分。",
    },
    {
        "metric_key": "tax_late_penalty_cnt",
        "name": "滞纳金/罚款笔数",
        "description": "滞纳金或罚款笔数，越高缴税纪律越差。",
        "metric_type": "simple",
        "formula": "tax_late_penalty_cnt",
        "unit": "笔",
        "grain": "enterprise",
        "source_fields": ["tax_late_penalty_cnt"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "",
    },
    {
        "metric_key": "void_invoice_cnt",
        "name": "作废发票笔数",
        "description": "作废发票笔数，占比过高为负向信号。",
        "metric_type": "simple",
        "formula": "void_invoice_cnt",
        "unit": "笔",
        "grain": "enterprise",
        "source_fields": ["void_invoice_cnt"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "",
    },
    {
        "metric_key": "unit_price_ratio",
        "name": "单价离散度",
        "description": "最高单价/均价，越大单价越离散（0=弃权）。",
        "metric_type": "simple",
        "formula": "unit_price_ratio",
        "unit": "倍",
        "grain": "enterprise",
        "source_fields": ["unit_price_ratio"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "0 表源缺失弃权。",
    },
    {
        "metric_key": "change_cnt",
        "name": "变更登记次数",
        "description": "工商/税务变更登记次数，越高经营稳定性越弱。",
        "metric_type": "simple",
        "formula": "change_cnt",
        "unit": "次",
        "grain": "enterprise",
        "source_fields": ["change_cnt"],
        "dimensions": ["industry_l1", "province", "time"],
        "default_filters": {},
        "edge_cases": "",
    },
]

_tables_ready = False


def _ensure_tables() -> bool:
    global _tables_ready
    if _tables_ready:
        return True
    try:
        from app.db.session import Base
        from app.db.urls import get_sync_engine
        from app.models.metric_registry import MetricDefinition

        Base.metadata.create_all(get_sync_engine(), tables=[MetricDefinition.__table__])
        _tables_ready = True
        return True
    except Exception as exc:
        logger.debug("metric_registry ensure_tables failed: %s", exc)
        return False


def ensure_canonical_metrics() -> int:
    """幂等写入规范口径字典；返回本次写入条数。规范指标系统所有，可安全覆盖更新。"""
    if not _ensure_tables():
        return 0
    try:
        from sqlalchemy.orm import Session

        from app.db.urls import get_sync_engine
        from app.models.metric_registry import MetricDefinition

        seeded = 0
        with Session(get_sync_engine()) as session:
            for m in CANONICAL_METRICS:
                rec = session.get(MetricDefinition, m["metric_key"])
                if rec is None:
                    rec = MetricDefinition(metric_key=m["metric_key"])
                    session.add(rec)
                    seeded += 1
                _apply_metric(rec, m)
                rec.is_canonical = True
                rec.updated_at = datetime.now(timezone.utc)
            session.commit()
        logger.info("canonical metrics ensured: %d new / %d total", seeded, len(CANONICAL_METRICS))
        return seeded
    except Exception as exc:
        logger.debug("ensure_canonical_metrics failed: %s", exc)
        return 0


def _apply_metric(rec, m: dict) -> None:
    rec.name = m["name"]
    rec.description = m["description"]
    rec.metric_type = m["metric_type"]
    rec.formula = m["formula"]
    rec.unit = m["unit"]
    rec.grain = m["grain"]
    rec.source_fields_json = json.dumps(m["source_fields"], ensure_ascii=False)
    rec.dimensions_json = json.dumps(m["dimensions"], ensure_ascii=False)
    rec.default_filters_json = json.dumps(m["default_filters"], ensure_ascii=False)
    rec.edge_cases = m["edge_cases"] or ""


def _metric_to_dict(rec) -> dict:
    return {
        "metric_key": rec.metric_key,
        "name": rec.name,
        "description": rec.description,
        "metric_type": rec.metric_type,
        "formula": rec.formula,
        "unit": rec.unit,
        "grain": rec.grain,
        "source_fields": _loads(rec.source_fields_json, []),
        "dimensions": _loads(rec.dimensions_json, []),
        "default_filters": _loads(rec.default_filters_json, {}),
        "edge_cases": rec.edge_cases or "",
        "is_canonical": bool(rec.is_canonical),
    }


def _loads(raw: str, default):
    try:
        return json.loads(raw) if raw else default
    except (TypeError, ValueError):
        return default


def build_dictionary(metrics: list) -> dict:
    """组装数据字典（querychat 模式）—— 只含元数据，供 LLM 上下文，不含任何原始数据/PII。"""
    return {
        "version": "1.0",
        "metrics": [_metric_to_dict(m) for m in metrics],
        "source_fields": SOURCE_FIELDS,
        "dimensions": [
            {"name": "industry_l1", "description": "行业大类（10 大类）"},
            {"name": "industry_l2", "description": "行业细类"},
            {"name": "province", "description": "省份"},
            {"name": "city", "description": "城市"},
            {"name": "scale_label", "description": "企业规模标签"},
            {"name": "time", "description": "时间粒度（月/年）"},
        ],
    }


# 运行时 Claim.value.metric 字符串 → 中文标签（统一 slice_report 与语义层的 metric 命名空间）。
# 动态指标（rank_* / seg_* / corr_* / compare_spread / risk_level_count 等）不在表内时回退到 metric 原名。
RUNTIME_METRIC_LABELS: dict[str, str] = {
    "avg_credit_score": "信用表现",
    "avg_revenue_yoy": "营收同比",
    "avg_authenticity_score": "经营真实性",
    "avg_score": "综合经营表现",
    "signal_total": "风险信号主体数",
    "coverage_count": "覆盖功能数",
    "benford_mad": "开票金额首位数字分布",
    "sample_count": "样本数",
    "session_synthesis_dims": "综合风控维度数",
    "session_overall_posture": "综合风险维度数",
    "avg_revenue_yoy_spread": "营收同比极差",
    "avg_credit_score_spread": "信用表现极差",
    "dim_tax_health": "税务健康",
    "dim_authenticity": "经营真实性",
    "dim_invoice": "发票健康",
    "dim_industry": "行业地位",
    "dim_legal": "法律合规",
    "dim_finance": "财务健康",
    "avg_composite": "发票舞弊",
    "signal_count": "信号主体数",
    "low_credit_industry_count": "低信用主体数",
    "risk_factor": "风险成因",
    "warning_signal_count": "预警信号项数",
    "peer_industry_percentile": "行业对标",
    "peer_province_percentile": "地区对标",
    "peer_scale_percentile": "规模对标",
    "overall_score": "综合经营表现",
    "credit_score": "信用表现",
    "revenue_yoy": "营收同比",
    "authenticity_score": "经营真实性",
    "revenue_deviation": "营收偏差",
    "profit_margin": "利润率",
    "profit_yoy": "利润同比",
    "debt_ratio": "资产负债率",
    "tax_on_time_rate": "纳税准时率",
    "fraud_composite_score": "发票舞弊",
    "customer_concentration": "客户集中度",
    "supplier_concentration": "供应商集中度",
    "category_concentration": "品目集中度",
    "vat_burden": "增值税税负率",
    "income_tax_burden": "所得税税负率",
    "correction_times": "申报更正次数",
    "social_headcount": "社保缴费人数",
    "tax_late_penalty_cnt": "滞纳金/罚款笔数",
    "void_invoice_cnt": "作废发票笔数",
    "unit_price_ratio": "单价离散度",
    "change_cnt": "变更登记次数",
    "financial_coverage": "财务覆盖率",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "roe": "净资产收益率",
    "roa": "总资产收益率",
    "asset_turnover": "总资产周转率",
    "receivables_turnover": "应收账款周转率",
    "inventory_turnover": "存货周转率",
    "flagged_count": "预警主体数",
    "risk_level": "群体风险判断",
    "high_severity_cnt": "高危信号数",
}


def zh_metric_label(metric: str | None) -> str | None:
    """运行时 metric → 业务中文名；未知英文/蛇形字段返回 None（禁止对外透出）。"""
    if not metric:
        return None
    if metric in RUNTIME_METRIC_LABELS:
        return RUNTIME_METRIC_LABELS[metric]
    try:
        from app.services.financial_benchmarks import FINANCIAL_RATIOS

        cfg = FINANCIAL_RATIOS.get(metric)
        if cfg and cfg.get("label"):
            return str(cfg["label"])
    except Exception:
        pass
    # 已是中文则放行
    if any("\u4e00" <= ch <= "\u9fff" for ch in metric):
        return metric
    return None


def format_surface_number(num: Any, unit: str = "", *, metric: str = "") -> str:
    """对外数字格式：计数字段出整数，其余去多余尾零。"""
    if num is None:
        return "—"
    try:
        f = float(num)
    except (TypeError, ValueError):
        return str(num)
    count_units = {"家", "次", "笔", "项", "人", "个", "条"}
    count_metric_suffixes = ("_cnt", "_count", "count", "hits", "flags")
    is_count = unit in count_units or any(metric.endswith(s) for s in count_metric_suffixes)
    if is_count:
        return str(int(round(f)))
    if abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f"{f:.4f}".rstrip("0").rstrip(".")

# 运行时 metric → 规范 metric_key（仅覆盖有明确对应关系的；其余映射到自身）。
RUNTIME_TO_CANONICAL: dict[str, str] = {
    "avg_credit_score": "credit_score",
    "avg_revenue_yoy": "revenue_yoy",
    "avg_authenticity_score": "authenticity_score",
    "avg_score": "overall_score",
    "overall_score": "overall_score",
    "dim_tax_health": "tax_health_score",
    "dim_authenticity": "authenticity_score",
    "dim_industry": "industry_score",
    "dim_legal": "legal_score",
    "dim_finance": "finance_score",
}

# 语义层可表达（可作为 metrics/group_by 目标）的规范 + 运行时指标全集，供 LLM 白名单。
ALLOWED_METRIC_KEYS: list[str] = sorted(
    {m["metric_key"] for m in CANONICAL_METRICS} | {"fraud_composite_score"}
)


def build_llm_dictionary() -> dict:
    """供 LLM 语义解析器的词汇表上下文：规范指标 + 源字段 + 维度 + 运行时指标标签。

    只含元数据，不含任何原始数据 / PII / 企业名；企业 id 一律为 MD5 哈希。
    """
    return {
        "version": "1.0",
        "metrics": CANONICAL_METRICS,
        "source_fields": SOURCE_FIELDS,
        "dimensions": [
            {"name": "industry_l1", "description": "行业大类"},
            {"name": "province", "description": "省份"},
            {"name": "scale_label", "description": "企业规模标签"},
            {"name": "time", "description": "时间粒度（月/年）"},
        ],
        "runtime_metrics": [
            {"metric": k, "label": v} for k, v in RUNTIME_METRIC_LABELS.items()
        ],
        "allowed_metrics": ALLOWED_METRIC_KEYS,
    }


# ── 风险信号阈值（唯一源，铁律：引擎/页面/模板一律引用，禁止写死数字）──
# 营收口径偏差（三口径离散度）预警阈值：>= 此值判「营收偏差过高」。
# 曾散落三处：信号分桶/热力图 25%、预警信号/洞察 A-01 30%、企划书 v1 20%，现统一收编。
REVENUE_DEVIATION_WARN = 0.30

# 多源交叉偏差（增值税/发票/财务三口径两两相对偏差）：异于 REVENUE_DEVIATION_WARN
# （后者是单字段 revenue_deviation）。真实性引擎 cross_source_deviation 唯一引用。
CROSS_AVG_DEVIATION_WARN = 0.25
CROSS_MAX_DEVIATION_WARN = 0.40


def revenue_deviation_warn_label() -> str:
    """营收偏差预警阈值中文标签（与 REVENUE_DEVIATION_WARN 同源，避免「≥25%」「30%」写死）。"""
    return f"营收偏差≥{int(REVENUE_DEVIATION_WARN * 100)}%"
