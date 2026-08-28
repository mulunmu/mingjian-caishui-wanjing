/** 报告章节 */
export interface ReportChapter {
  id: string;
  title: string;
  description: string;
  conclusion: string;
  evidence_chain: string[];
  chart?: {
    type: string;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    data: any;
  };
}

/** 报告（前端展示用） */
export interface Report {
  id: string;
  title: string;
  subtitle: string;
  dimension: string;
  function: string;
  generated_at: string;
  summary: string;
  chapters: ReportChapter[];
}

/** 后端报告列表项 */
export interface ReportListItem {
  report_id: string;
  title: string;
  date: string;
  size: number;
  download_url: string;
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
  validation?: Record<string, unknown>;
  download_url: string;
}

/** 报告生成参数（适配后端） */
export interface ReportParams {
  scenario?: string;
  session_id?: string;
  query?: string;
}

/** 邮件发送参数（适配后端） */
export interface EmailReportParams {
  recipient: string;
  scenario?: string;
  session_id?: string;
}
