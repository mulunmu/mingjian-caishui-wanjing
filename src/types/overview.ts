/** 后端 /risk/summary 响应 */
export interface RiskSummaryResponse {
  sample_count: number;
  high_risk_count: number;
  avg_score: number;
  warning_count: number;
  risk_distribution: Record<string, number>;
  enterprises: {
    enterprise_id: string;
    display_label: string;
    risk_level: string;
    overall_score: number;
    industry_l1: string;
  }[];
}

/** 后端 /risk/warnings 响应中的企业条目 */
export interface WarningEnterprise {
  enterprise_id: string;
  display_label: string;
  enterprise_name?: string;
  industry_l1?: string;
  risk_level?: string;
  overall_score?: number;
  warning_signals: string[];
}

/** 前端 KPI 统计 */
export interface OverviewKpi {
  sample_count: number;
  high_risk_count: number;
  avg_score: number;
  warning_count: number;
}

/** 风险等级分布项 */
export interface RiskDistItem {
  name: string;
  value: number;
}
