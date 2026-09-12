import { create } from 'zustand';
import type { Report, ReportListItem, ReportParams, EmailReportParams, ReportValidation } from '@/types/report';
import { reportApi } from '@/api/report';

function apiErrorMessage(e: unknown, fallback: string): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
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
  sendEmail: (params: EmailReportParams) => Promise<boolean>;
  clearReport: () => void;
}

const useReportStore = create<ReportStore>((set) => ({
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

  sendEmail: async (params) => {
    try {
      const res = await reportApi.sendEmail(params);
      return res.success;
    } catch {
      console.error('发送失败');
      return false;
    }
  },

  clearReport: () => set({ currentReport: null }),
}));

export default useReportStore;
