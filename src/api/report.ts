import client from './client';
import type {
  Report,
  ReportParams,
  ReportListResponse,
  ReportGenerateResponse,
  EmailReportParams,
} from '@/types/report';

export const reportApi = {
  /** 列出已生成的报告 */
  list: (): Promise<ReportListResponse> =>
    client.get('/report/list'),

  /** 生成报告（切片模式） */
  generate: (params: ReportParams): Promise<ReportGenerateResponse> =>
    client.post('/report/generate', {
      scenario: params.scenario || 'general',
      session_id: params.session_id,
      query: params.query,
      industry_l1: params.industry_l1,
      province: params.province,
    }),

  /** 生成切片报告 */
  slice: (params: ReportParams): Promise<ReportGenerateResponse> =>
    client.post('/report/slice', {
      scenario: params.scenario,
      session_id: params.session_id,
      query: params.query,
      industry_l1: params.industry_l1,
      province: params.province,
    }),

  /** 生成企业深度报告 */
  enterprise: (enterpriseId: string): Promise<ReportGenerateResponse> =>
    client.post('/report/enterprise', { enterprise_id: enterpriseId }),

  /** 向导预校验：生成前判定样本/章节是否可用 */
  validateWizard: (params: {
    scenario?: string;
    industry_l1?: string;
    province?: string;
    enterprise_id?: string;
  }): Promise<{
    ok: boolean;
    reason?: string;
    mode?: string;
    scenario?: string;
    scope_sample_count?: number;
    available_chapter_count?: number;
  }> => client.post('/report/validate-wizard', params),

  /** HTML 预览 */
  preview: (params: ReportParams): Promise<string> =>
    client.post('/report/preview', {
      scenario: params.scenario,
      session_id: params.session_id,
      query: params.query,
    }),

  /** 报告结构化详情（与下载 PDF 同源快照回读） */
  get: (id: string): Promise<Report> => client.get(`/report/${id}`),

  /** 删除报告（PDF + 附属文件），仅 owner/admin */
  remove: (id: string): Promise<{ success: boolean; message: string }> =>
    client.delete(`/report/${id}`),

  /** 下载 PDF */
  downloadPdf: (reportId: string): Promise<Blob> =>
    client.get(`/report/${reportId}/download`, { responseType: 'blob' }),

  /** 邮件发送报告（适配后端接口） */
  sendEmail: (params: EmailReportParams): Promise<{ success: boolean; message?: string; report_id?: string }> =>
    client.post('/report/email', {
      recipient: params.recipient,
      scenario: params.scenario || 'general',
      session_id: params.session_id,
    }),
};
