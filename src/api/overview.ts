import client from './client';
import type {
  RiskSummaryResponse,
  WarningEnterprise,
  OverviewKpi,
  RiskDistItem,
  IndustryProfileItem,
} from '@/types/overview';

/** 信号代码 → 中文标签 */
export const SIGNAL_LABELS: Record<string, string> = {
  tax_on_time_rate_low: '纳税准时率偏低',
  invoice_monthly_avg_drop: '月均开票额骤降',
  credit_level_risk: '信用等级 C/D/M',
  social_trend_shrink: '社保趋势缩减',
  revenue_deviation_high: '营收偏差过高',
  legal_compliance_risk: '法律合规分偏低',
  legal_enforcement_risk: '失信/被执行',
};

/** 信号代码 → 严重等级 */
export const SIGNAL_LEVELS: Record<string, 'high' | 'medium' | 'low'> = {
  tax_on_time_rate_low: 'high',
  invoice_monthly_avg_drop: 'high',
  credit_level_risk: 'high',
  social_trend_shrink: 'medium',
  revenue_deviation_high: 'medium',
  legal_compliance_risk: 'high',
  legal_enforcement_risk: 'high',
};

export function translateSignal(code: string): { label: string; level: 'high' | 'medium' | 'low' } {
  return {
    label: SIGNAL_LABELS[code] || code,
    level: SIGNAL_LEVELS[code] || 'medium',
  };
}

export interface OverviewData {
  kpi: OverviewKpi;
  riskDistribution: RiskDistItem[];
  industryDistribution: RiskDistItem[];
  industryProfiles: IndustryProfileItem[];
  warnings: WarningEnterprise[];
  topWarningsTotal: number;
}

/** 空态：不伪造演示数据。失败时由 getData 抛错，由 store 展示错误态。 */
export class OverviewUnavailableError extends Error {
  constructor(message = '风控总览暂不可用，请稍后重试。') {
    super(message);
    this.name = 'OverviewUnavailableError';
  }
}

export const overviewApi = {
  getData: async (topN = 10): Promise<OverviewData> => {
    try {
      const summary: RiskSummaryResponse = await client.get(`/risk/summary?top_n=${topN}`);

      // 优先用 summary.top_warnings；缺省时再拉 /warnings?limit（兼容旧后端）
      let warnings: WarningEnterprise[] = Array.isArray(summary.top_warnings)
        ? summary.top_warnings
        : [];
      let topWarningsTotal =
        typeof summary.top_warnings_total === 'number'
          ? summary.top_warnings_total
          : warnings.length;

      if (warnings.length === 0) {
        try {
          const res = await client.get(`/risk/warnings?high_risk_only=true&limit=${topN}`);
          warnings = Array.isArray(res) ? res : [];
          topWarningsTotal = warnings.length;
        } catch {
          // 预警接口可选：summary 成功即可渲染 KPI
        }
      }

      const riskDistribution = Object.entries(summary.risk_distribution || {}).map(
        ([name, value]) => ({ name, value }),
      );

      let industryDistribution: RiskDistItem[] = [];
      if (summary.industry_distribution && Object.keys(summary.industry_distribution).length) {
        industryDistribution = Object.entries(summary.industry_distribution)
          .map(([name, value]) => ({ name, value }))
          .sort((a, b) => b.value - a.value);
      } else {
        const indMap = new Map<string, number>();
        for (const e of summary.enterprises || []) {
          const key = e.industry_l1 || '其他';
          indMap.set(key, (indMap.get(key) || 0) + 1);
        }
        industryDistribution = Array.from(indMap.entries())
          .map(([name, value]) => ({ name, value }))
          .sort((a, b) => b.value - a.value);
      }

      return {
        kpi: {
          sample_count: summary.sample_count,
          high_risk_count: summary.high_risk_count,
          avg_score: summary.avg_score,
          warning_count: summary.warning_count,
          conclusion: summary.conclusion,
          top_warnings_total: topWarningsTotal,
        },
        riskDistribution,
        industryDistribution,
        industryProfiles: summary.industry_profiles || [],
        warnings,
        topWarningsTotal,
      };
    } catch (e) {
      if (e instanceof OverviewUnavailableError) throw e;
      throw new OverviewUnavailableError(
        e instanceof Error ? e.message : '风控总览暂不可用，请稍后重试。',
      );
    }
  },

  /** 展开「查看全部」时再拉全量高风险（仍可带 limit 上限） */
  getAllHighRisk: async (limit = 200): Promise<WarningEnterprise[]> => {
    const res = await client.get(`/risk/warnings?high_risk_only=true&limit=${limit}`);
    return Array.isArray(res) ? res : [];
  },
};
