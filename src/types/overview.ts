/** 后端 /risk/summary 响应 */
export interface RiskSummaryResponse {
  sample_count: number;
  high_risk_count: number;
  avg_score: number;
  warning_count: number;
  risk_distribution: Record<string, number>;
  industry_profiles?: IndustryProfileItem[];
  enterprises: {
    enterprise_id: string;
    display_label: string;
    display_name?: string;
    risk_level: string;
    overall_score: number;
    industry_l1: string;
  }[];
}

/** 行业画像对标项（集中度/税负率 0-1，展示层 ×100） */
export interface IndustryProfileItem {
  industry_l1: string;
  n: number;
  customer_concentration: number | null;
  supplier_concentration: number | null;
  category_concentration: number | null;
  vat_burden: number | null;
  income_tax_burden: number | null;
}

/** 后端 /risk/warnings 响应中的企业条目 */
export interface WarningEnterprise {
  enterprise_id: string;
  display_label: string;
  display_name?: string;
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
