"""企业财务三表宽表 + 四能力比率（一企业一行）。

源：syx_tax_finance_profit_year（利润表）/ syx_tax_finance_balance_year（资产负债表）
    / syx_cash_flow（现金流量表），行项目名经 U() 修复乱码后由 ETL 精确匹配。
设计铁律：
- 原始行项目金额（元）落库用于报告章节溯源与展示，不直接参与打分口径；
- 四能力比率（偿债/营运/盈利/成长）由 ETL 计算层统一算出，客观评级与之绑定；
- 分母绝对值低于阈值时置 0（弃权），不伪造比率。
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EnterpriseFinancials(Base):
    """三大报表行项目 + 四能力比率（脱敏，仅匿名 enterprise_id）。"""

    __tablename__ = "enterprise_financials"

    enterprise_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # MD5(taxpayer_id)
    report_year: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 最新报告期，如 2023

    # ── 资产负债表（元）──
    total_assets: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 资产总计
    total_liab: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)        # 负债合计
    current_assets: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)    # 流动资产合计
    current_liab: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 流动负债合计
    cash_equiv: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)        # 货币资金
    inventory: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)         # 存货
    accounts_receivable: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 应收账款
    fixed_assets: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 固定资产净额
    short_loan: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)        # 短期借款
    owner_equity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 所有者权益合计
    retained_earnings: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 未分配利润

    # ── 利润表（元）──
    revenue: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)           # 营业收入
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)              # 营业成本
    tax_surcharge: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)     # 税金及附加
    sell_expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 销售费用
    admin_expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)     # 管理费用
    finance_expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)   # 财务费用
    operating_profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 营业利润
    total_profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 利润总额
    income_tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)        # 所得税费用
    net_profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)        # 净利润

    # ── 现金流量表（元）──
    operating_cf: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 经营活动现金流量净额
    investing_cf: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 投资活动现金流量净额
    financing_cf: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 筹资活动现金流量净额

    # ── 四能力比率 ──
    # 偿债能力
    current_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)     # 流动比率
    quick_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)       # 速动比率
    debt_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)        # 资产负债率
    # 营运能力（周转次数/年）
    receivables_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)  # 应收账款周转率
    inventory_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)    # 存货周转率
    asset_turnover: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)        # 总资产周转率
    # 盈利能力
    gross_margin: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)      # 毛利率
    net_margin: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)        # 净利率
    roe: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)               # 净资产收益率
    roa: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)               # 总资产收益率
    # 成长能力
    revenue_yoy: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)       # 营收同比
    profit_yoy: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)        # 净利润同比

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
