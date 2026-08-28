import { create } from 'zustand';
import type { Report, ReportListItem, ReportParams, EmailReportParams } from '@/types/report';
import { reportApi } from '@/api/report';

interface ReportStore {
  currentReport: Report | null;
  reportList: ReportListItem[];
  isGenerating: boolean;
  isLoadingList: boolean;
  listError: string | null;

  fetchReportList: () => Promise<void>;
  generateReport: (params: ReportParams) => Promise<string>;
  generateSlice: (scenario: string) => Promise<string>;
  fetchReport: (id: string) => Promise<void>;
  downloadPdf: (id: string) => Promise<void>;
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
    } catch {
      set({ isGenerating: false });
      throw new Error('报告生成失败');
    }
  },

  generateSlice: async (scenario) => {
    set({ isGenerating: true });
    try {
      const res = await reportApi.slice({ scenario });
      set({ isGenerating: false });
      return res.report_id;
    } catch {
      set({ isGenerating: false });
      throw new Error('报告生成失败');
    }
  },

  fetchReport: async (id) => {
    const report = await reportApi.get(id);
    set({ currentReport: report });
  },

  downloadPdf: async (id) => {
    try {
      const blob = await reportApi.downloadPdf(id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report-${id}.pdf`;
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
