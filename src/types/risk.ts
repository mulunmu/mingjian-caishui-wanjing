/** 同业基准组定位 */
export interface PeerGroupPosition {
  label: string;
  value: string;
  peer_total: number;
  rank: number;
  percentile: number;
  group_mean: number;
  deviation: number;
  score: number;
}

/** 同业基准响应 */
export interface PeerBenchmark {
  enterprise_id: string;
  overall_score: number;
  groups: {
    industry: PeerGroupPosition;
    province: PeerGroupPosition;
    scale: PeerGroupPosition;
  };
}

/** 维度详情 */
export interface DimensionDetail {
  score: number;
  weight: number;
  label: string;
  effective_weight?: number;
  event_count?: number;
  coverage?: string;
  coverage_note?: string;
}

/** 归因维度 */
export interface AttributionDimension {
  score: number;
  weight: number;
  label: string;
  positive: { item: string; contribution: number }[];
  negative: { item: string; deduction: number; count?: number }[];
  net_contribution: number;
}

/** 企业画像（后端实际返回结构） */
export interface EnterpriseProfile {
  enterprise_id: string;
  enterprise_name: string;
  display_label: string;
  credit_level?: string;
  tax_on_time_rate?: number;
  invoice_monthly_avg?: number;
  revenue_deviation?: number;
  social_trend?: string;
  industry_l1?: string;
  industry_l2?: string;
  province?: string;
  city?: string;
  overall_score: number;
  risk_level: string;
  dimensions: {
    tax_health: number;
    authenticity: number;
    invoice: number;
    industry: number;
    legal: number;
    finance: number;
  };
  dimension_details: Record<string, DimensionDetail>;
  attribution: {
    dimensions: Record<string, AttributionDimension>;
    summary: string;
  };
  warning_signals: string[];
  [key: string]: unknown;
}

/** 洞察研判（多指标联动，规则引擎产出） */
export interface Insight {
  rule_id: string;
  category: string;
  title: string;
  severity: '高危' | '预警';
  fact: string;
  advice: string;
}

/** TOP-N 明细（对手方/品目） */
export interface TopItem {
  name: string;
  taxno?: string;
  amount?: number;
  share?: number;
}

/** 发票画像（后端 invoice_profile） */
export interface InvoiceProfile {
  sales_invoice_cnt: number;
  purchase_invoice_cnt: number;
  sales_amount: number;
  purchase_amount: number;
  red_invoice_cnt: number;
  void_invoice_cnt: number;
  abnormal_invoice_cnt: number;
  category_count: number;
  top_category_name: string;
  top_category_share: number;
  top_categories: TopItem[];
  customer_count: number;
  top_customer_name: string;
  top_customer_share: number;
  customer_hhi: number;
  top_customers: TopItem[];
  supplier_count: number;
  top_supplier_name: string;
  top_supplier_share: number;
  supplier_hhi: number;
  top_suppliers: TopItem[];
  avg_unit_price: number;
  max_unit_price: number;
}

/** 税务画像（后端 tax_profile） */
export interface TaxProfile {
  vat_sales_amount: number;
  vat_payable: number;
  vat_burden: number;
  income_tax_payable: number;
  income_tax_burden: number;
  total_tax_paid: number;
  tax_late_penalty_amount: number;
  tax_late_penalty_cnt: number;
  correction_times: number;
  correction_records: number;
  correction_levy_count: number;
  social_headcount: number;
  social_insured_count: number;
  social_payment_base: number;
  social_monthly_payment: number;
  tax_loan_amount: number;
  tax_loan_balance: number;
  tax_loan_success_cnt: number;
  tax_loan_apply_cnt: number;
  tax_loan_success_rate: number;
  tax_preference_amount: number;
  rd_expense: number;
  is_high_tech: boolean;
  payroll_amount: number;
  investor_cnt: number;
  top_investor_share: number;
  change_cnt: number;
}

/** 杜邦分解因子 */
export interface DupontFactor {
  field: string;
  label: string;
  dir: string;
  is_pct: boolean;
  value: number | null;
  disp: string | null;
}

/** 杜邦分解（ROE = 净利率 × 总资产周转率 × 权益乘数） */
export interface DupontBreakdown {
  complete: boolean;
  factors: DupontFactor[];
  roe: number | null;
  roe_disp: string | null;
  formula: string;
}

/** 财务画像（后端 financial） */
export interface FinancialProfile {
  report_year: string;
  dupont?: DupontBreakdown | null;
  balance_sheet: {
    total_assets: number;
    total_liab: number;
    current_assets: number;
    current_liab: number;
    cash_equiv: number;
    inventory: number;
    accounts_receivable: number;
    fixed_assets: number;
    short_loan: number;
    owner_equity: number;
    retained_earnings: number;
  };
  income_statement: {
    revenue: number;
    cost: number;
    tax_surcharge: number;
    sell_expense: number;
    admin_expense: number;
    finance_expense: number;
    operating_profit: number;
    total_profit: number;
    income_tax: number;
    net_profit: number;
  };
  cash_flow: {
    operating_cf: number;
    investing_cf: number;
    financing_cf: number;
  };
  ratios: {
    current_ratio: number;
    quick_ratio: number;
    debt_ratio: number;
    receivables_turnover: number;
    inventory_turnover: number;
    asset_turnover: number;
    gross_margin: number;
    net_margin: number;
    roe: number;
    roa: number;
    revenue_yoy: number;
    profit_yoy: number;
  };
}

/** 异动信号（差异驱动：高危/预警/较上期恶化/新增） */
export interface AnomalySignal {
  signal_id: string;
  tag: '高危' | '预警' | '较上期恶化' | '新增';
  category: string;
  title: string;
  level: 'high' | 'medium' | 'low';
  evidence: string;
  advice: string;
  trace: { table: string; field: string };
}

/** 企业画像响应 */
export interface EnterpriseProfileResponse {
  profile: EnterpriseProfile;
  peer_benchmark: PeerBenchmark;
  insights?: Insight[];
  invoice_profile?: InvoiceProfile | null;
  tax_profile?: TaxProfile | null;
  financial?: FinancialProfile | null;
  anomaly_signals?: AnomalySignal[];
}

/** 反欺诈分析结果 */
export interface FraudAnalysisItem {
  enterprise_id: string;
  display_label?: string;
  display_name?: string;
  industry_l1?: string;
  fraud_composite_score?: number;
  fraud_risk_level?: string;
  fraud_signals?: Record<string, unknown>;
  scbm_mismatch_score?: number;
  red_invoice_score?: number;
  concentration_score?: number;
  [key: string]: unknown;
}

/** 经营真实性分析结果 */
export interface AuthenticityItem {
  enterprise_id: string;
  display_label?: string;
  display_name?: string;
  industry_l1?: string;
  authenticity_score?: number;
  cross_avg_deviation?: number;
  cross_suspicious?: boolean;
  [key: string]: unknown;
}

/** 预警信号 */
export interface WarningItem {
  id?: string;
  label?: string;
  title?: string;
  count?: number;
  level?: 'high' | 'medium' | 'low';
  icon?: string;
  type?: string;
  description?: string;
  [key: string]: unknown;
}

/** 指标字典项 */
export interface MetricDefinition {
  metric_key: string;
  name: string;
  description?: string;
  metric_type?: string;
  formula?: string;
  unit?: string;
  grain?: string;
  source_fields?: string[];
  dimensions?: string[];
  [key: string]: unknown;
}

/** 指标字典接口响应：后端返回对象（metrics 为真实口径数组），而非扁平数组 */
export interface MetricDictionaryResponse {
  version: string;
  metrics: MetricDefinition[];
  source_fields?: unknown[];
  dimensions?: unknown[];
}
