/** 溯源字符串（table.field）→ 中文可读标签。未命中的表/字段原样展示，不隐藏证据。 */

const TABLE_LABELS: Record<string, string> = {
  core_metrics: '核心指标',
  enterprise_financials: '企业财务报表',
  enterprise_engine_features: '企业引擎特征',
  enterprise_profile: '企业档案',
  industry_benchmark: '行业基准',
  field_mappings: '字段映射',
  syx_invoice: '发票',
  syx_invoice_details: '发票明细',
  syx_red_invoices_info: '红字发票',
};

const FIELD_LABELS: Record<string, string> = {
  overall_score: '综合评分',
  risk_level: '风险等级',
  credit_level: '信用等级',
  revenue_deviation: '营收偏差',
  tax_on_time_rate: '纳税准时率',
  vat_burden: '增值税税负',
  income_tax_burden: '所得税税负',
  tax_late_penalty_cnt: '滞纳/处罚次数',
  tax_violation_cnt: '税务违法次数',
  arrears_cnt: '欠税次数',
  gross_margin: '毛利率',
  net_margin: '净利率',
  debt_ratio: '资产负债率',
  current_ratio: '流动比率',
  quick_ratio: '速动比率',
  roe: '净资产收益率',
  roa: '总资产收益率',
  receivables_turnover: '应收账款周转率',
  inventory_turnover: '存货周转率',
  asset_turnover: '总资产周转率',
  revenue_yoy: '营收同比',
  profit_yoy: '净利同比',
  operating_cf: '经营现金流',
  fraud_composite_score: '舞弊综合分',
  scbm_mismatch_score: '进销错配分',
  red_invoice_score: '红字发票分',
  concentration_score: '集中度分',
  industry_l1: '行业大类',
  province: '地区',
  scbm: '税控编码',
  display_label: '匿名标签',
  void_ratio: '红冲发票占比',
};

/** 把 `core_metrics.tax_on_time_rate` 转成 `核心指标 · 纳税准时率`。 */
export function translateTrace(trace: string | null | undefined): string {
  if (!trace) return '—';
  const dot = trace.indexOf('.');
  if (dot === -1) {
    return TABLE_LABELS[trace] || FIELD_LABELS[trace] || trace;
  }
  const table = trace.slice(0, dot);
  const field = trace.slice(dot + 1);
  const tableLabel = TABLE_LABELS[table] || table;
  const fieldLabel = field ? FIELD_LABELS[field] || field : '';
  return fieldLabel ? `${tableLabel} · ${fieldLabel}` : tableLabel;
}

/** 单个来源名（如 `core_metrics` / `fraud`）→ 中文。 */
export function translateSource(source: string | null | undefined): string {
  if (!source) return '';
  if (source === 'fraud') return '反欺诈引擎';
  if (source === 'computed') return '系统计算';
  if (source === 'industry_benchmark') return '行业基准';
  return TABLE_LABELS[source] || source;
}
