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
  isLoading: boolean;
  error: string | null;
  fetchOverview: () => Promise<void>;
}

const useOverviewStore = create<OverviewStore>((set) => ({
  kpi: null,
  riskDistribution: [],
  industryDistribution: [],
  industryProfiles: [],
  warnings: [],
  isLoading: false,
  error: null,

  fetchOverview: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await overviewApi.getData();
      set({
        kpi: data.kpi,
        riskDistribution: data.riskDistribution,
        industryDistribution: data.industryDistribution,
        industryProfiles: data.industryProfiles,
        warnings: data.warnings,
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
        error: e instanceof Error ? e.message : '风控总览暂不可用',
      });
    }
  },
}));

export default useOverviewStore;
