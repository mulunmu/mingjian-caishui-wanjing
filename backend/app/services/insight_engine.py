"""洞察引擎：多指标联动研判（规则引擎，确定性，不经 LLM）。

从 CoreMetrics + EnterpriseEngineFeatures 产出结构化洞察结论（研判），
每条洞察锚定真实字段、可溯源，供个体深度报告「洞察研判」章节使用。

设计铁律（与《报告设计规范 v1》一致）：
- 触发条件与客观评级与场景无关：同一批数据 → 同一批洞察，不因立场而变；
- 洞察只改表达、不改事实；数字只来自计算层；弃权优先于编造（features 缺失时跳过）；
- 发票舞弊阈值复用 fraud/authenticity 引擎自身的信号判定（fraud_signals），不另设黑盒阈值。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core_metrics import CoreMetrics
from app.models.engine_store import EnterpriseEngineFeatures
from app.schemas.claim import Claim, ClaimTrace, ClaimValue
from app.services.metric_registry import REVENUE_DEVIATION_WARN, revenue_deviation_warn_label

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"高危": 0, "预警": 1}
CATEGORY_LABELS = {
    "财务": "财务",
    "税务": "税务",
    "发票": "发票",
    "真实性": "真实性",
    "司法": "司法",
    "综合": "综合",
}


def _f(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _present(v: Any) -> bool:
    """比率/占比字段：0 为弃权哨兵（与 financial_benchmarks 一致），不得当真实 0 参与判定。"""
    return _f(v) != 0.0


@dataclass
class Evidence:
    """单条证据：锚定表字段的可溯源数字。value 存原始量纲（比率 0-1、金额为元）。"""

    label: str
    value: float | int | str | bool
    unit: str = ""
    table: str = "core_metrics"
    field: str = ""

    def scaled(self) -> float | int | str | bool:
        if isinstance(self.value, bool) or isinstance(self.value, str):
            return self.value
        return round(float(self.value) * 100, 2) if self.unit == "%" else self.value

    def render(self) -> str:
        if isinstance(self.value, bool):
            return f"{self.label}={'是' if self.value else '否'}"
        if isinstance(self.value, str):
            return f"{self.label}={self.value}"
        # 字段已知 → 走财务比率字典（倍数/百分比口径唯一源，禁止空 unit 启发式篡改）
        if self.field:
            from app.services.financial_benchmarks import FINANCIAL_RATIOS, format_financial_ratio

            if self.field in FINANCIAL_RATIOS:
                return f"{self.label} {format_financial_ratio(self.field, self.value)}"
        if self.unit == "%":
            return f"{self.label} {float(self.value) * 100:.1f}%"
        if self.unit in ("家", "次", "笔", "项", "人", "个", "条"):
            return f"{self.label} {int(round(float(self.value)))}{self.unit}"
        # 显式偏差率字段（无 % unit 的遗留）：仅白名单可 ×100，禁止把流动比率等倍数误当百分比
        if (
            self.unit == ""
            and self.field in {
                "revenue_deviation",
                "cross_deviation",
                "cross_avg_deviation",
                "authenticity_gap",
            }
            and isinstance(self.value, (int, float))
            and 0 < abs(float(self.value)) < 1
        ):
            return f"{self.label} {float(self.value) * 100:.1f}%"
        if isinstance(self.value, (int, float)) and abs(float(self.value) - round(float(self.value))) < 1e-9:
            return f"{self.label} {int(round(float(self.value)))}{self.unit}"
        return f"{self.label} {float(self.value):.2f}{self.unit}"


@dataclass
class Insight:
    rule_id: str
    category: str  # 财务/税务/发票/真实性/司法/综合
    title: str  # 研判结论
    severity: str  # 高危/预警
    evidence: list[Evidence] = field(default_factory=list)
    advice: str = ""

    @property
    def primary(self) -> Evidence | None:
        return self.evidence[0] if self.evidence else None

    def fact_text(self) -> str:
        return "，".join(e.render() for e in self.evidence)


def _signals(features: EnterpriseEngineFeatures | None) -> set[str]:
    if features is None:
        return set()
    try:
        raw = features.fraud_signals or "[]"
        arr = json.loads(raw) if isinstance(raw, str) else raw
        return {str(s) for s in arr or []}
    except Exception:
        return set()


def _pct(label: str, value: Any, field: str, table: str = "core_metrics") -> Evidence:
    return Evidence(label, round(_f(value), 4), "%", table, field)


def _cnt(label: str, value: Any, field: str, table: str = "core_metrics") -> Evidence:
    return Evidence(label, int(_f(value)), "次", table, field)


def _score(label: str, value: Any, field: str) -> Evidence:
    return Evidence(label, round(_f(value), 2), "", "enterprise_engine_features", field)


# ---------------------------------------------------------------------------
# 财务模块（有三大报表样本 → 四能力比率规则；无 → 代理口径 F-01~F-04）
# ---------------------------------------------------------------------------


def _r_f01_debt(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    from app.services.financial_benchmarks import FINANCIAL_RATIOS

    if not _present(m.debt_ratio):
        return None
    thr = float(FINANCIAL_RATIOS["debt_ratio"]["warn_threshold"])
    if _f(m.debt_ratio) <= thr:
        return None
    return Insight(
        "F-01", "财务", "偿债承压", "预警",
        [_pct("资产负债率", m.debt_ratio, "debt_ratio")],
        f"资产负债率高于 {thr * 100:.0f}%，偿债压力偏大，建议授信时关注其负债结构与再融资能力。",
    )


def _r_f02_cashflow(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    # 现金流净额允许真实 0；仅 None 不可达（列 default=0）。负值才预警。
    if _f(m.cash_flow_net) >= 0:
        return None
    return Insight(
        "F-02", "财务", "经营现金流净流出", "预警",
        [Evidence("经营现金流净额", round(_f(m.cash_flow_net), 2), "元", "core_metrics", "cash_flow_net")],
        "经营现金流为负，账面盈利或未转化为现金回笼，建议结合回款周期评估真实流动性。",
    )


def _r_f03_revenue_not_profit(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not (_present(m.revenue_yoy) and _present(m.profit_margin)):
        return None
    if not (_f(m.revenue_yoy) > 0.1 and _f(m.profit_margin) < 0.05):
        return None
    return Insight(
        "F-03", "财务", "增收不增利", "预警",
        [_pct("营收同比", m.revenue_yoy, "revenue_yoy"), _pct("利润率", m.profit_margin, "profit_margin")],
        "营收增长但利润率偏低，增收未转化为盈利，建议关注成本费用与真实盈利能力。",
    )


def _r_f04_revenue_slump(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not _present(m.revenue_yoy):
        return None
    if _f(m.revenue_yoy) >= -0.2:
        return None
    return Insight(
        "F-04", "财务", "营收显著下滑", "预警",
        [_pct("营收同比", m.revenue_yoy, "revenue_yoy")],
        "营收同比大幅下滑，经营收缩明显，建议核实下滑原因与持续经营能力。",
    )


def _r_f05_current_ratio(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not getattr(m, "has_financial_statements", False):
        return None
    cr = _f(m.current_ratio)
    if cr <= 0 or cr >= 1.0:
        return None
    return Insight(
        "F-05", "财务", "流动比率偏低", "预警",
        [Evidence("流动比率", round(cr, 2), "", "core_metrics", "current_ratio")],
        "流动比率低于1，短期偿债能力不足，建议关注短期流动性风险。",
    )


def _r_f06_quick_ratio(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not getattr(m, "has_financial_statements", False):
        return None
    qr = _f(m.quick_ratio)
    if qr <= 0 or qr >= 0.5:
        return None
    return Insight(
        "F-06", "财务", "速动比率偏低", "预警",
        [Evidence("速动比率", round(qr, 2), "", "core_metrics", "quick_ratio")],
        "速动比率低于0.5，剔除存货后短期偿债能力弱，建议关注变现能力。",
    )


def _r_f07_receivables_turnover(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not getattr(m, "has_financial_statements", False):
        return None
    rt = _f(m.receivables_turnover)
    if rt <= 0 or rt >= 2.0:
        return None
    return Insight(
        "F-07", "财务", "应收账款周转偏慢", "预警",
        [Evidence("应收账款周转率(次/年)", round(rt, 2), "", "core_metrics", "receivables_turnover")],
        "应收账款周转率低于2次/年，回款周期偏长，建议关注坏账与占款风险。",
    )


def _r_f08_inventory_turnover(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not getattr(m, "has_financial_statements", False):
        return None
    it = _f(m.inventory_turnover)
    if it <= 0 or it >= 2.0:
        return None
    return Insight(
        "F-08", "财务", "存货周转偏慢", "预警",
        [Evidence("存货周转率(次/年)", round(it, 2), "", "core_metrics", "inventory_turnover")],
        "存货周转率低于2次/年，存货积压风险，建议关注滞销与减值。",
    )


def _r_f09_roe_negative(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not getattr(m, "has_financial_statements", False):
        return None
    roe = _f(m.roe)
    if roe >= 0:
        return None
    return Insight(
        "F-09", "财务", "净资产收益率为负", "预警",
        [_pct("净资产收益率", m.roe, "roe")],
        "净资产收益率为负，本期亏损侵蚀所有者权益，建议关注持续经营能力。",
    )


def _r_f10_gross_margin_low(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not getattr(m, "has_financial_statements", False):
        return None
    gm = _f(m.gross_margin)
    if gm <= 0 or gm >= 0.1:
        return None
    return Insight(
        "F-10", "财务", "毛利率偏低", "预警",
        [_pct("毛利率", m.gross_margin, "gross_margin")],
        "毛利率低于10%，盈利能力偏弱，建议关注成本控制与真实定价能力。",
    )


# ---------------------------------------------------------------------------
# 税务模块
# ---------------------------------------------------------------------------


def _r_t01_arrears(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if int(m.tax_arrears_cnt or 0) <= 0:
        return None
    return Insight(
        "T-01", "税务", "存在欠税", "高危",
        [_cnt("欠税次数", m.tax_arrears_cnt, "tax_arrears_cnt")],
        "存在欠税记录，税务合规风险高，建议核实欠税金额与清缴情况。",
    )


def _r_t02_violation(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    viol = int(m.tax_violation_cnt or 0)
    high = int(m.high_severity_cnt or 0)
    if viol <= 0 and high <= 0:
        return None
    return Insight(
        "T-02", "税务", "税务违法记录", "高危",
        [_cnt("税务违法次数", viol, "tax_violation_cnt"), _cnt("高危事件次数", high, "high_severity_cnt")],
        "存在税务违法/高危事件，合规风险突出，建议调取处罚详情。",
    )


def _r_t03_credit(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if (m.credit_level or "") not in ("D", "M"):
        return None
    return Insight(
        "T-03", "税务", "纳税信用偏低", "预警",
        [Evidence("纳税信用等级", m.credit_level, "", "core_metrics", "credit_level"),
         Evidence("信用分", round(_f(m.credit_score), 2), "分", "core_metrics", "credit_score")],
        "纳税信用等级偏低，反映历史合规表现不佳，建议关注其申报与缴纳规范。",
    )


def _r_t04_on_time(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not _present(m.tax_on_time_rate):
        return None
    if _f(m.tax_on_time_rate) >= 0.8:
        return None
    return Insight(
        "T-04", "税务", "纳税准时率偏低", "预警",
        [_pct("纳税准时率", m.tax_on_time_rate, "tax_on_time_rate")],
        "纳税准时率低于 80%，存在迟缴习惯，建议关注现金流与申报规范。",
    )


def _r_t05_late_penalty(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if int(m.tax_late_penalty_cnt or 0) <= 0:
        return None
    return Insight(
        "T-05", "税务", "存在滞纳金/罚款", "预警",
        [_cnt("滞纳金/罚款笔数", m.tax_late_penalty_cnt, "tax_late_penalty_cnt")],
        "存在税款滞纳金或罚款记录，反映申报缴纳规范性不足，建议核实发生原因与金额。",
    )


def _r_t06_correction_frequent(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if int(m.correction_times or 0) < 80:
        return None
    return Insight(
        "T-06", "税务", "申报更正异常频繁", "预警",
        [_cnt("申报更正次数", m.correction_times, "correction_times")],
        "申报更正次数显著高于同类企业，存在申报质量不稳定或反复调整嫌疑，建议核查更正明细。",
    )


def _r_t07_vat_burden_low(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    vb = _f(m.vat_burden)
    if not (0 < vb < 0.005):
        return None
    return Insight(
        "T-07", "税务", "增值税税负率明显偏低", "预警",
        [_pct("增值税税负率", m.vat_burden, "vat_burden")],
        "增值税税负率低于 0.5%，明显低于各行业安全税负区间下限，建议核查进销项与收入申报完整性。",
    )


def _r_t08_income_tax_burden_low(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    ib = _f(m.income_tax_burden)
    if not (0 < ib < 0.001):
        return None
    return Insight(
        "T-08", "税务", "所得税税负率明显偏低", "预警",
        [_pct("所得税税负率", m.income_tax_burden, "income_tax_burden")],
        "企业所得税税负率（应纳所得税额/营业收入）低于 0.1%，利润贡献不足，建议核查成本费用与利润真实性。",
    )


def _r_t10_change_frequent(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if int(m.change_cnt or 0) < 15:
        return None
    return Insight(
        "T-10", "税务", "变更登记频繁", "预警",
        [_cnt("变更登记次数", m.change_cnt, "change_cnt")],
        "工商变更登记次数显著高于同类企业（离群值），经营主体稳定性不足，建议关注控制权与股权结构变化。",
    )


# ---------------------------------------------------------------------------
# 发票舞弊模块（复用 fraud 引擎信号判定）
# ---------------------------------------------------------------------------


def _r_i01_scbm(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if "scbm_mismatch" not in _signals(feats):
        return None
    return Insight(
        "I-01", "发票", "进销品目错配", "高危",
        [_score("品目错配分", feats.scbm_mismatch_score, "scbm_mismatch_score")],
        "进销商品税控编码错配，涉嫌发票品目异常，建议核查进销一致性。",
    )


def _r_i02_red(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    sig = "red_invoice" in _signals(feats)
    red_cnt = int(m.red_invoice_cnt or 0)
    inv_cnt = int(m.invoice_cnt or 0)
    ratio = (red_cnt / inv_cnt) if inv_cnt > 0 else 0.0
    if not sig and ratio <= 0.1:
        return None
    ev = [_cnt("红冲次数", red_cnt, "red_invoice_cnt"), _cnt("开票次数", inv_cnt, "invoice_cnt")]
    if feats is not None:
        ev.append(_score("红冲异常分", feats.red_invoice_score, "red_invoice_score"))
    return Insight(
        "I-02", "发票", "红字发票异常", "高危",
        ev,
        "红字发票占比异常，涉嫌虚开/冲销，建议调取红冲明细核查。",
    )


def _r_i03_concentration(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if "concentration" not in _signals(feats):
        return None
    return Insight(
        "I-03", "发票", "开票集中度偏高", "预警",
        [_score("集中度分", feats.concentration_score, "concentration_score")],
        "开票集中度过高，交易对手单一，建议关注关联交易与依赖风险。",
    )


def _r_i04_sequence(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if "sequence_gap" not in _signals(feats):
        return None
    return Insight(
        "I-04", "发票", "发票序列缺口异常", "预警",
        [Evidence("序列缺口率", round(_f(feats.sequence_gap_ratio), 4), "", "enterprise_engine_features", "sequence_gap_ratio")],
        "发票号码序列跳号异常，存在拆票/断号风险，建议核查开票连续性。",
    )


def _r_i05_composite(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if feats is None:
        return None
    lvl = feats.fraud_risk_level or "低风险"
    score = _f(feats.fraud_composite_score)
    if lvl not in ("高风险", "中高风险") and score < 70:
        return None
    sev = "高危" if lvl == "高风险" else "预警"
    return Insight(
        "I-05", "发票", "综合舞弊风险偏高", sev,
        [_score("综合舞弊分", score, "fraud_composite_score"), Evidence("舞弊风险等级", lvl, "", "enterprise_engine_features", "fraud_risk_level")],
        "综合舞弊评分偏高、多信号叠加，建议纳入重点核查名单。",
    )


def _r_i06_customer_concentration(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if _f(m.customer_concentration) <= 0.5:
        return None
    return Insight(
        "I-06", "发票", "单一客户重大依赖", "预警",
        [_pct("第一大客户金额占比", m.customer_concentration, "customer_concentration")],
        "第一大客户销售占比超过 50%，对该客户存在重大依赖，业绩受其波动影响显著，建议核查其稳定性与回款。",
    )


def _r_i07_supplier_concentration(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if _f(m.supplier_concentration) <= 0.5:
        return None
    return Insight(
        "I-07", "发票", "单一供应商重大依赖", "预警",
        [_pct("第一大供应商金额占比", m.supplier_concentration, "supplier_concentration")],
        "第一大供应商采购占比超过 50%，供应链集中度过高，存在断供与议价风险，建议关注其稳定性。",
    )


def _r_i08_bilateral(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not (_f(m.customer_concentration) > 0.5 and _f(m.supplier_concentration) > 0.5):
        return None
    return Insight(
        "I-08", "发票", "进销双边集中", "高危",
        [_pct("第一大客户占比", m.customer_concentration, "customer_concentration"),
         _pct("第一大供应商占比", m.supplier_concentration, "supplier_concentration")],
        "购销两端均高度集中，疑似空转、过票或关联交易，建议核查交易真实性与资金流。",
    )


def _r_i09_single_category(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if _f(m.category_concentration) <= 0.9:
        return None
    return Insight(
        "I-09", "发票", "经营品类高度单一", "预警",
        [_pct("第一大品目金额占比", m.category_concentration, "category_concentration")],
        "开票品目高度单一（单一品目占比超 90%），经营结构单一，建议结合进销两端判断真实业务实质。",
    )


def _r_i10_void_invoice(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    void_cnt = int(m.void_invoice_cnt or 0)
    inv_cnt = int(m.invoice_cnt or 0)
    ratio = (void_cnt / inv_cnt) if inv_cnt > 0 else 0.0
    if ratio <= 0.15:
        return None
    return Insight(
        "I-10", "发票", "作废发票占比异常", "预警",
        [_cnt("作废发票笔数", void_cnt, "void_invoice_cnt"), _cnt("开票笔数", inv_cnt, "invoice_cnt")],
        "作废发票占比超过 15%，显著高于正常错票作废水平，涉嫌虚开或开票管理混乱，建议核查作废原因。",
    )


def _r_i11_unit_price_dispersion(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    ratio = _f(m.unit_price_ratio)
    if ratio <= 100000:
        return None
    return Insight(
        "I-11", "发票", "单价离散异常", "预警",
        [Evidence("最高单价/均价", round(ratio, 2), "", "core_metrics", "unit_price_ratio")],
        "最高单价达均价的 10 万倍以上，单价离散度过高，疑似品目归类或单价异常，建议核查发票明细。",
    )


# ---------------------------------------------------------------------------
# 真实性模块
# ---------------------------------------------------------------------------


def _r_a01_deviation(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not _present(m.revenue_deviation):
        return None
    # 与 assessment._warning_signals 统一阈值（见 metric_registry.REVENUE_DEVIATION_WARN）
    if _f(m.revenue_deviation) < REVENUE_DEVIATION_WARN:
        return None
    return Insight(
        "A-01", "真实性", "多源营收口径背离", "预警",
        [_pct("营收偏差", m.revenue_deviation, "revenue_deviation")],
        f"多源营收口径背离超过 {int(REVENUE_DEVIATION_WARN * 100)}%，数据真实性存疑，建议交叉核对申报口径。",
    )


def _r_a02_cross(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if feats is None or not feats.cross_suspicious:
        return None
    ev = [Evidence("交叉验证可疑", True, "", "enterprise_engine_features", "cross_suspicious")]
    if feats.cross_avg_deviation is not None:
        ev.append(Evidence("交叉偏差率", round(_f(feats.cross_avg_deviation), 4), "", "enterprise_engine_features", "cross_avg_deviation"))
    return Insight(
        "A-02", "真实性", "多源交叉验证可疑", "高危",
        ev,
        "多源交叉验证可疑，营收数据自洽性不足，建议核实申报数据。",
    )


def _r_a03_authenticity(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if feats is None or _f(feats.authenticity_score) >= 40:
        return None
    return Insight(
        "A-03", "真实性", "真实性评分偏低", "预警",
        [_score("真实性分", feats.authenticity_score, "authenticity_score")],
        "真实性评分偏低，数据质量存疑，建议审慎采信财务数据。",
    )


# ---------------------------------------------------------------------------
# 司法 / 综合
# ---------------------------------------------------------------------------


def _r_r01_dishonesty(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not m.is_dishonesty:
        return None
    return Insight(
        "R-01", "司法", "失信被执行人", "高危",
        [Evidence("失信标志", True, "", "core_metrics", "is_dishonesty")],
        "列入失信被执行人名单，司法风险高，建议审慎。",
    )


def _r_r02_execution(m: CoreMetrics, feats: EnterpriseEngineFeatures | None) -> Insight | None:
    if not m.is_execution:
        return None
    return Insight(
        "R-02", "司法", "被执行记录", "预警",
        [Evidence("被执行标志", True, "", "core_metrics", "is_execution")],
        "存在被执行记录，司法执行风险，建议关注执行标的。",
    )


_BASE_RULES = [
    _r_f01_debt,
    _r_f02_cashflow,
    _r_f03_revenue_not_profit,
    _r_f04_revenue_slump,
    _r_f05_current_ratio,
    _r_f06_quick_ratio,
    _r_f07_receivables_turnover,
    _r_f08_inventory_turnover,
    _r_f09_roe_negative,
    _r_f10_gross_margin_low,
    _r_t01_arrears,
    _r_t02_violation,
    _r_t03_credit,
    _r_t04_on_time,
    _r_t05_late_penalty,
    _r_t06_correction_frequent,
    _r_t07_vat_burden_low,
    _r_t08_income_tax_burden_low,
    _r_t10_change_frequent,
    _r_i01_scbm,
    _r_i02_red,
    _r_i03_concentration,
    _r_i04_sequence,
    _r_i05_composite,
    _r_i06_customer_concentration,
    _r_i07_supplier_concentration,
    _r_i08_bilateral,
    _r_i09_single_category,
    _r_i10_void_invoice,
    _r_i11_unit_price_dispersion,
    _r_a01_deviation,
    _r_a02_cross,
    _r_a03_authenticity,
    _r_r01_dishonesty,
    _r_r02_execution,
]


def evaluate_insights(
    metrics: CoreMetrics,
    features: EnterpriseEngineFeatures | None,
) -> list[Insight]:
    """确定性评估：命中则返回 Insight，未命中返回 None 规则被过滤。"""
    insights = [r(metrics, features) for r in _BASE_RULES]
    insights = [i for i in insights if i is not None]

    high = [i for i in insights if i.severity == "高危"]
    if len(high) >= 2:
        # 对外只展示中文标题，禁止 rule_id（T-01/A-02）漏进报告正文
        fired = "、".join(i.title for i in high)
        insights.append(
            Insight(
                "R-03",
                "综合",
                "多重风险叠加",
                "高危",
                [
                    Evidence("高危信号数", len(high), "项", "core_metrics", "risk_level"),
                    Evidence("叠加项", fired, "", "core_metrics", "risk_level"),
                ],
                "多项高危信号叠加，整体风险显著偏高，建议审慎并优先核查。",
            )
        )

    insights.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 9), i.rule_id))
    return insights


def insights_to_dict(insights: list[Insight]) -> list[dict[str, Any]]:
    """序列化洞察，供 API / 前端「洞察研判」卡片渲染。"""
    return [
        {
            "rule_id": i.rule_id,
            "category": i.category,
            "title": i.title,
            "severity": i.severity,
            "fact": i.fact_text(),
            "advice": i.advice,
        }
        for i in insights
    ]


def insights_to_claims(
    insights: list[Insight],
    short_id: str,
    label: str,
) -> list[Claim]:
    """把洞察转成可溯源的 Claim，接入既有报告章节管线。"""
    claims: list[Claim] = []
    for ins in insights:
        primary = ins.primary
        fact = ins.fact_text()
        text = f"{ins.title}（{ins.severity}）：{fact}。{ins.advice}"
        value = None
        trace = None
        if primary is not None:
            trace = ClaimTrace(
                table=primary.table or "core_metrics",
                field=primary.field or ins.rule_id,
                query_id=f"Q_insight_{ins.rule_id.replace('-', '_').lower()}",
            )
            if isinstance(primary.value, (int, float)) and not isinstance(primary.value, bool):
                value = ClaimValue(metric=ins.rule_id, number=primary.scaled(), unit=primary.unit)
        claims.append(
            Claim(
                claim=text,
                value=value,
                trace=trace,
                confidence="computed",
                evidence_chain=[e.render() for e in ins.evidence],
            )
        )
    return claims


async def load_insight_inputs(
    db: AsyncSession,
    enterprise_id: str,
) -> tuple[CoreMetrics | None, EnterpriseEngineFeatures | None]:
    """加载个体洞察所需的两张表（CoreMetrics + 引擎特征）。

    数据不可得时返回 (None, None)，由调用方弃权（不编造洞察）。
    """
    if db is None:
        return None, None
    metrics = await db.get(CoreMetrics, enterprise_id)
    features = await db.get(EnterpriseEngineFeatures, enterprise_id)
    return metrics, features
