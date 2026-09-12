/** 报告章节 */
export interface ReportChapter {
  id: string;
  title: string;
  description: string;
  conclusion: string;
  evidence_chain: string[];
  narration?: string;
  // 企业报告合成章节的附加字段（可选）
  points?: string[];
  advantages?: string[];
  advice?: string[];
  risk_level?: string;
  metrics?: Array<{ label: string; value: string; unit: string; rating?: string }>;
  chart?: {
    type: string;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    data: any;
  };
}

/** 封面 KPI 卡（含来源溯源） */
export interface ReportKpi {
  label: string;
  value: string;
  unit: string;
  source?: string;
  trace?: string;
}

/** 报告（前端展示用） */
export interface Report {
  id: string;
  title: string;
  subtitle: string;
  scenario?: string;
  dimension?: string;
  function?: string;
  generated_at: string;
  summary: string;
  kpis: ReportKpi[];
  chapters: ReportChapter[];
  story?: string;
  validation?: ReportValidation;
}

/** 报告抗幻觉 / 门禁校验结果（与后端 validation 同源） */
export interface ReportValidation {
  ok?: boolean;
  empty?: boolean;
  total_claims?: number;
  unanchored?: number;
  number_unanchored?: number;
  risk_contradictions?: number;
  details?: Array<Record<string, unknown>>;
  enforced?: Record<string, unknown>;
  cross_enforced?: Record<string, unknown>;
  cross_surface?: Record<string, unknown>;
}

/** 后端报告列表项 */
export interface ReportListItem {
  report_id: string;
  title: string;
  date: string;
  size: number;
  download_url: string;
  enterprise_id?: string | null;
}

/** 后端报告列表响应 */
export interface ReportListResponse {
  items: ReportListItem[];
  total: number;
  source: string;
}

/** 后端报告生成响应 */
export interface ReportGenerateResponse {
  report_id: string;
  status: string;
  title: string;
  scenario?: string;
  validation?: ReportValidation;
  download_url: string;
}

/** 报告生成参数（适配后端） */
export interface ReportParams {
  scenario?: string;
  session_id?: string;
  query?: string;
  industry_l1?: string;
  province?: string;
}

/** 邮件发送参数（适配后端） */
export interface EmailReportParams {
  recipient: string;
  scenario?: string;
  session_id?: string;
}
