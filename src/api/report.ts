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
    }),

  /** 生成切片报告 */
  slice: (params: ReportParams): Promise<ReportGenerateResponse> =>
    client.post('/report/slice', {
      scenario: params.scenario,
      session_id: params.session_id,
      query: params.query,
    }),

  /** 生成企业深度报告 */
  enterprise: (enterpriseId: string): Promise<ReportGenerateResponse> =>
    client.post('/report/enterprise', { enterprise_id: enterpriseId }),

  /** HTML 预览 */
  preview: (params: ReportParams): Promise<string> =>
    client.post('/report/preview', {
      scenario: params.scenario,
      session_id: params.session_id,
      query: params.query,
    }),

  /** 从列表元数据组装详情（后端无 GET /report/:id；禁止伪造章节分数） */
  get: async (id: string): Promise<Report> => {
    const list = (await client.get('/report/list')) as ReportListResponse;
    const item = (list.items || []).find((i) => i.report_id === id);
    if (!item) {
      throw new Error('报告不存在或无权访问');
    }
    return {
      id: item.report_id,
      title: item.title,
      subtitle: 'PDF 交付物',
      dimension: '—',
      function: '—',
      generated_at: item.date,
      summary: '报告已生成。完整分析内容请下载 PDF 查看。',
      chapters: [],
    };
  },

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
