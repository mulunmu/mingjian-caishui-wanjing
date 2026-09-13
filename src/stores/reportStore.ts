import { create } from 'zustand';
import type { Report, ReportListItem, ReportParams, ReportValidation } from '@/types/report';
import { reportApi } from '@/api/report';
import { emailApi } from '@/api/email';

function apiErrorMessage(e: unknown, fallback: string): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}

/** 发送结果：ok=false 且 needVerify=true 表示收件邮箱未受信、需补验证码。 */
export interface SendResult {
  ok: boolean;
  message: string;
  needVerify?: boolean;
  sent?: number;
  failed?: number;
}

export interface SendEmailParams {
  report_id: string;
  recipient: string;
  code?: string;
  remember?: boolean;
}

export interface BatchEmailParams {
  report_ids: string[];
  recipient: string;
  code?: string;
  remember?: boolean;
}

interface ReportStore {
  currentReport: Report | null;
  reportList: ReportListItem[];
  isGenerating: boolean;
  isLoadingList: boolean;
  listError: string | null;

  fetchReportList: () => Promise<void>;
  generateReport: (params: ReportParams) => Promise<string>;
  generateSlice: (params: {
    scenario: string;
    industry_l1?: string;
    province?: string;
  }) => Promise<{ reportId: string; validation?: ReportValidation }>;
  fetchReport: (id: string) => Promise<void>;
  downloadPdf: (id: string, title?: string) => Promise<void>;
  deleteReport: (reportId: string) => Promise<void>;
  sendEmail: (params: SendEmailParams) => Promise<SendResult>;
  batchEmail: (params: BatchEmailParams) => Promise<SendResult>;
  clearReport: () => void;
}

const useReportStore = create<ReportStore>((set, get) => ({
  currentReport: null,
  reportList: [],
  isGenerating: false,
  isLoadingList: false,
  listError: null,

  fetchReportList: async () => {
    set({ isLoadingList: true, listError: null });
    try {
      const res = await reportApi.list();
      set({ reportList: res.items || [], isLoadingList: false, listError: null });
    } catch (e) {
      set({
        reportList: [],
        isLoadingList: false,
        listError: e instanceof Error ? e.message : '报告列表暂不可用',
      });
    }
  },

  generateReport: async (params) => {
    set({ isGenerating: true });
    try {
      const res = await reportApi.generate(params);
      set({ isGenerating: false });
      return res.report_id;
    } catch (e) {
      set({ isGenerating: false });
      throw new Error(apiErrorMessage(e, '报告生成失败'));
    }
  },

  generateSlice: async (params) => {
    set({ isGenerating: true });
    try {
      const res = await reportApi.slice(params);
      set({ isGenerating: false });
      return { reportId: res.report_id, validation: res.validation as ReportValidation | undefined };
    } catch (e) {
      set({ isGenerating: false });
      throw new Error(apiErrorMessage(e, '报告生成失败'));
    }
  },

  fetchReport: async (id) => {
    const report = await reportApi.get(id);
    set({ currentReport: report });
  },

  downloadPdf: async (id, title) => {
    try {
      const blob = await reportApi.downloadPdf(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title || '评估报告'}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      console.error('下载失败');
    }
  },

  deleteReport: async (reportId) => {
    try {
      await reportApi.remove(reportId);
      // 删除后同步列表；若当前正查看该报告则清空
      if (get().currentReport?.id === reportId) set({ currentReport: null });
      await get().fetchReportList();
    } catch (e) {
      throw new Error(apiErrorMessage(e, '删除失败'));
    }
  },

  sendEmail: async (params) => {
    try {
      const res = await emailApi.send(params);
      return { ok: true, message: res.message };
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      return { ok: false, message: apiErrorMessage(e, '发送失败'), needVerify: status === 428 };
    }
  },

  batchEmail: async (params) => {
    try {
      const res = await emailApi.batch(params);
      return {
        ok: res.failed === 0,
        message: `成功 ${res.sent} 份，失败 ${res.failed} 份`,
        sent: res.sent,
        failed: res.failed,
      };
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      return { ok: false, message: apiErrorMessage(e, '批量发送失败'), needVerify: status === 428 };
    }
  },

  clearReport: () => set({ currentReport: null }),
}));

export default useReportStore;
