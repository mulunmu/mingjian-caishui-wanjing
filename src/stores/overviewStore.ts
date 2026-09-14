import { create } from 'zustand';
import type {
  OverviewKpi,
  RiskDistItem,
  WarningEnterprise,
  IndustryProfileItem,
} from '@/types/overview';
import { overviewApi } from '@/api/overview';

interface OverviewStore {
  kpi: OverviewKpi | null;
  riskDistribution: RiskDistItem[];
  industryDistribution: RiskDistItem[];
  industryProfiles: IndustryProfileItem[];
  warnings: WarningEnterprise[];
  topWarningsTotal: number;
  showAllAlerts: boolean;
  isLoading: boolean;
  isExpanding: boolean;
  error: string | null;
  fetchOverview: () => Promise<void>;
  expandAllAlerts: () => Promise<void>;
  collapseAlerts: () => void;
}

const TOP_N = 10;

const useOverviewStore = create<OverviewStore>((set, get) => ({
  kpi: null,
  riskDistribution: [],
  industryDistribution: [],
  industryProfiles: [],
  warnings: [],
  topWarningsTotal: 0,
  showAllAlerts: false,
  isLoading: false,
  isExpanding: false,
  error: null,

  fetchOverview: async () => {
    set({ isLoading: true, error: null, showAllAlerts: false });
    try {
      const data = await overviewApi.getData(TOP_N);
      set({
        kpi: data.kpi,
        riskDistribution: data.riskDistribution,
        industryDistribution: data.industryDistribution,
        industryProfiles: data.industryProfiles,
        warnings: data.warnings,
        topWarningsTotal: data.topWarningsTotal,
        isLoading: false,
        error: null,
      });
    } catch (e) {
      set({
        isLoading: false,
        kpi: null,
        riskDistribution: [],
        industryDistribution: [],
        industryProfiles: [],
        warnings: [],
        topWarningsTotal: 0,
        error: e instanceof Error ? e.message : '风控总览暂不可用',
      });
    }
  },

  expandAllAlerts: async () => {
    if (get().isExpanding || get().showAllAlerts) return;
    set({ isExpanding: true });
    try {
      const all = await overviewApi.getAllHighRisk(200);
      set({
        warnings: all,
        topWarningsTotal: Math.max(get().topWarningsTotal, all.length),
        showAllAlerts: true,
        isExpanding: false,
      });
    } catch {
      // 展开失败时仍展示已有 TopN
      set({ showAllAlerts: true, isExpanding: false });
    }
  },

  collapseAlerts: () => {
    set({ showAllAlerts: false });
    void get().fetchOverview();
  },
}));

export default useOverviewStore;
