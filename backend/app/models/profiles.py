"""发票画像 / 税务画像宽表（一企业一行，脱敏，供报告章节溯源与展示）。

源：
- EnterpriseInvoiceProfile ← syx_invoice / syx_invoice_details / syx_red_invoices_info
- EnterpriseTaxProfile    ← syx_tax_payment / syx_tax_value_added / syx_corporate_income_year*
                            / syx_declaration_correction / syx_social_declaration
                            / syx_tax_interaction / syx_investor_info / syx_enterprise_change_info

设计铁律（同 [[financials]]）：
- 金额（元）落库用于溯源展示，不直接参与打分口径；
- 集中度/占比/税负率由 ETL 计算层统一算出，客观评级与之绑定；
- 分母绝对值低于阈值时置 0（弃权），不伪造比率；
- TOP-N 明细（客户/供应商/品目）以 JSON 文本落库，供报告展示，不做热路径打分。
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EnterpriseInvoiceProfile(Base):
    """发票画像：进销项规模、品目聚合、客户/供应商集中度、单价、红字/作废/异常凭证。"""

    __tablename__ = "enterprise_invoice_profile"

    enterprise_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # MD5(taxpayer_id)

    # ── 进销项规模 ──
    sales_invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)      # 销项发票数
    purchase_invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)   # 进项发票数
    sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)    # 销项价税合计（元）
    purchase_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 进项价税合计（元）

    # ── 红字 / 作废 / 异常凭证 ──
    red_invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)        # 已红冲发票数（state=2）
    void_invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)       # 作废发票数（state=1）
    abnormal_invoice_cnt: Mapped[int] = mapped_column(Integer, default=0)   # 异常凭证数（risk_level=异常凭证）

    # ── 品目聚合（按税收分类编码前4位 scbm4，TOP 结构） ──
    category_count: Mapped[int] = mapped_column(Integer, default=0)         # 品目（scbm4）种类数
    top_category_name: Mapped[str] = mapped_column(String(120), default="")  # TOP1 品目（商品名称）
    top_category_share: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # TOP1 品目金额占比
    top_categories_json: Mapped[str | None] = mapped_column(Text, nullable=True)    # TOP5 [{name, amount, share}]

    # ── 客户集中度（销项 → 购方） ──
    customer_count: Mapped[int] = mapped_column(Integer, default=0)         # 客户（购方）家数
    top_customer_name: Mapped[str] = mapped_column(String(120), default="")  # TOP1 客户名称
    top_customer_share: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # TOP1 客户金额占比
    customer_hhi: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # 客户 HHI
    top_customers_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # TOP5 [{name, taxno, amount, share}]

    # ── 供应商集中度（进项 → 销方） ──
    supplier_count: Mapped[int] = mapped_column(Integer, default=0)         # 供应商（销方）家数
    top_supplier_name: Mapped[str] = mapped_column(String(120), default="")  # TOP1 供应商名称
    top_supplier_share: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # TOP1 供应商金额占比
    supplier_hhi: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # 供应商 HHI
    top_suppliers_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # TOP5 [{name, taxno, amount, share}]

    # ── 单价（销项明细，不含税单价 bw_spdj / 含税 hsdj） ──
    avg_unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)  # 加权平均单价（金额/数量）
    max_unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)  # 最高单价

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EnterpriseTaxProfile(Base):
    """税务画像：税负率、完税诚信、申报更正、社保、银税互动融资、优惠/研发/股权结构。"""

    __tablename__ = "enterprise_tax_profile"

    enterprise_id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # ── 增值税 ──
    vat_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 应税销售额（元）
    vat_payable: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)       # 应纳税额合计（元）
    vat_burden: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)         # 增值税税负率 = 应纳税额/销售额

    # ── 企业所得税 ──
    income_tax_payable: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 应纳所得税额（元）
    income_tax_burden: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)    # 所得税税负率

    # ── 完税（syx_tax_payment） ──
    total_tax_paid: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)      # 已缴税款合计（元）
    tax_late_penalty_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 滞纳金+罚款（元）
    tax_late_penalty_cnt: Mapped[int] = mapped_column(Integer, default=0)           # 滞纳金/罚款笔数

    # ── 申报更正（syx_declaration_correction） ──
    correction_times: Mapped[int] = mapped_column(Integer, default=0)               # 已更正次数（MAX already_change_times）
    correction_records: Mapped[int] = mapped_column(Integer, default=0)             # 更正记录条数
    correction_levy_count: Mapped[int] = mapped_column(Integer, default=0)          # 更正涉及征收项目数

    # ── 社保（syx_social_declaration） ──
    social_headcount: Mapped[int] = mapped_column(Integer, default=0)               # 缴费人数（最新）
    social_insured_count: Mapped[int] = mapped_column(Integer, default=0)           # 参保人数（最新）
    social_payment_base: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 缴费基数（最新，元）
    social_monthly_payment: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 月均应缴费额（元）

    # ── 银税互动融资（syx_tax_interaction） ──
    tax_loan_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)     # 贷款金额合计（元）
    tax_loan_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)    # 贷款余额合计（元）
    tax_loan_success_cnt: Mapped[int] = mapped_column(Integer, default=0)           # 授信/授权成功次数
    tax_loan_apply_cnt: Mapped[int] = mapped_column(Integer, default=0)             # 申请次数
    tax_loan_success_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)  # 授信成功率

    # ── 优惠 / 研发 / 高新（企业所得税汇算清缴附表） ──
    tax_preference_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)  # 减免所得税额（jmsds）
    rd_expense: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)           # 研发费用（yffy）
    is_high_tech: Mapped[bool] = mapped_column(Boolean, default=False)               # 高新技术企业（gxjs 有记录）
    payroll_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)       # 职工薪酬账载金额（zgxc）

    # ── 股权 / 变更 ──
    investor_cnt: Mapped[int] = mapped_column(Integer, default=0)                    # 投资方家数
    top_investor_share: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)    # 第一大投资方比例
    change_cnt: Mapped[int] = mapped_column(Integer, default=0)                      # 变更登记次数

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
