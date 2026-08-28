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

/** 企业画像响应 */
export interface EnterpriseProfileResponse {
  profile: EnterpriseProfile;
  peer_benchmark: PeerBenchmark;
}

/** 反欺诈分析结果 */
export interface FraudAnalysisItem {
  enterprise_id: string;
  display_label?: string;
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
