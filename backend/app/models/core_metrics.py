from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CoreMetrics(Base):
    """一企业一行：匿名税务宽表（无上市公司字段、无明文企业名）"""

    __tablename__ = "core_metrics"

    enterprise_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # MD5(taxpayer_id)
    display_label: Mapped[str] = mapped_column(String(120))  # 地区·行业大类·规模
    display_name: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 可读名「企业N」（匿名但仍可串联单企业分析）
    industry_l1: Mapped[str] = mapped_column(String(50))  # 6 大类
    industry_l2: Mapped[str] = mapped_column(String(80))  # 原始行业细类
    province: Mapped[str] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(50))
    scale_label: Mapped[str] = mapped_column(String(20), default="小微")

    # ① 税务健康
    credit_level: Mapped[str] = mapped_column(String(10), default="暂无")
    credit_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    tax_on_time_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    tax_arrears_cnt: Mapped[int] = mapped_column(Integer, default=0)
    tax_violation_cnt: Mapped[int] = mapped_column(Integer, default=0)
    high_severity_cnt: Mapped[int] = mapped_column(Integer, default=0)
    is_dishonesty: Mapped[bool] = mapped_column(Boolean, default=False)
    is_execution: Mapped[bool] = mapped_column(Boolean, default=False)
    loan_cnt: Mapped[int] = mapped_column(Integer, default=0)
    loan_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    # ② 真实性 / 发票
    vat_revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    invoice_revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    finance_revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    revenue_deviation: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    invoice_monthly_avg: Mapped[int] = mapped_column(Integer, default=0)
    invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)
    red_invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)
    social_trend: Mapped[str] = mapped_column(String(10), default="稳定")
    social_months: Mapped[int] = mapped_column(Integer, default=0)

    # ④ 财务（非上市口径：利润率/增速/负债/现金流）
    profit_margin: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    revenue_yoy: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    profit_yoy: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    cash_flow_net: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    cash_flow_level: Mapped[str] = mapped_column(String(10), default="一般")

    # ④′ 财务四能力比率（由三大报表 ETL 计算，denormalize 供评分/洞察热路径）
    current_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)          # 流动比率
    quick_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)            # 速动比率
    gross_margin: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)           # 毛利率
    net_margin: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)             # 净利率
    roe: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)                    # 净资产收益率
    roa: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)                    # 总资产收益率
    receivables_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)   # 应收账款周转率
    inventory_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)     # 存货周转率
    asset_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)         # 总资产周转率
    has_financial_statements: Mapped[bool] = mapped_column(Boolean, default=False)     # 是否抽取到完整三大报表

    # ⑤ 发票画像（Phase 2，集中度 0-1，0=弃权）
    customer_concentration: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # 客户 TOP1 金额占比
    supplier_concentration: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # 供应商 TOP1 金额占比
    category_concentration: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # 品目 TOP1 金额占比

    # ⑤′ 发票质量 + 单价离散（Phase 2 回填，0=弃权）
    void_invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)                  # 作废发票笔数
    unit_price_ratio: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)       # 最高单价/均价（单价离散度）

    # ⑥ 税务画像（Phase 3，税负率 0-1，0=弃权）
    vat_burden: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)              # 增值税税负率
    income_tax_burden: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)       # 所得税税负率
    correction_times: Mapped[int] = mapped_column(Integer, default=0)                  # 申报更正次数
    social_headcount: Mapped[int] = mapped_column(Integer, default=0)                  # 社保缴费人数（最新）
    tax_late_penalty_cnt: Mapped[int] = mapped_column(Integer, default=0)              # 滞纳金/罚款笔数
    change_cnt: Mapped[int] = mapped_column(Integer, default=0)                        # 变更登记次数（经营稳定性）

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 兼容旧代码读取 enterprise_name：优先可读名「企业N」，缺失回退 地区·行业·规模
    @property
    def enterprise_name(self) -> str:
        return self.display_name or self.display_label

    # 兼容旧 assessment 中的 z_score_level（roe 现为真实列，见上方四能力比率）
    @property
    def z_score_level(self) -> str:
        mapping = {"健康": "安全", "一般": "灰色", "承压": "困境"}
        return mapping.get(self.cash_flow_level, "灰色")

    @property
    def z_score(self) -> Decimal:
        mapping = {"健康": Decimal("3.5"), "一般": Decimal("2.0"), "承压": Decimal("1.0")}
        return mapping.get(self.cash_flow_level, Decimal("2.0"))


class IndustryBenchmark(Base):
    """分行业大类基准（均值 / 分位）"""

    __tablename__ = "industry_benchmark"

    industry_l1: Mapped[str] = mapped_column(String(50), primary_key=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_credit_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    avg_tax_on_time_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    avg_revenue_deviation: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    avg_invoice_monthly: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    avg_profit_margin: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    avg_debt_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    p50_credit_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    p50_invoice_monthly: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    high_risk_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    # 财务四能力比率基准（行业均值，供风险态势「行业财务对标」）
    avg_current_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_quick_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_gross_margin: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_net_margin: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_roe: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_roa: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_receivables_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_inventory_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    avg_asset_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LegalEvent(Base):
    """税务违法等事件（由 syx_tax_illega 等 ETL 写入）"""

    __tablename__ = "legal_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enterprise_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(1), nullable=False, default="M")
    amount_involved: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
