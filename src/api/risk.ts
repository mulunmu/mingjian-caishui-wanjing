import client from './client';
import type {
  EnterpriseProfileResponse,
  FraudAnalysisItem,
  AuthenticityItem,
  WarningItem,
  MetricDefinition,
  MetricDictionaryResponse,
} from '@/types/risk';

/** 后端 fraud/authenticity 返回批次对象，不是数组；在此归一化为行列表。 */
export interface FraudBatchResponse {
  sample_count?: number;
  flagged_count?: number;
  avg_composite?: number;
  top_flags?: Record<string, unknown>[];
  coverage?: string;
  [key: string]: unknown;
}

export interface AuthenticityBatchResponse {
  sample_count?: number;
  suspicious_count?: number;
  avg_authenticity_score?: number;
  top_suspicious?: Record<string, unknown>[];
  [key: string]: unknown;
}

function mapRiskLevel(raw: unknown): string | undefined {
  const s = String(raw || '').trim();
  if (!s) return undefined;
  if (s === 'high' || s.includes('高')) return 'high';
  if (s === 'medium' || s.includes('中')) return 'medium';
  if (s === 'low' || s.includes('低')) return 'low';
  // 未知等级弃权，禁止默认「中风险」误报
  return undefined;
}

/** 将 /risk/fraud 批次响应当成表格行（top_flags）。失败由调用方处理，不伪造行。 */
export function normalizeFraudRows(res: unknown): FraudAnalysisItem[] {
  if (Array.isArray(res)) return res as FraudAnalysisItem[];
  if (!res || typeof res !== 'object') return [];
  const batch = res as FraudBatchResponse;
  const flags = Array.isArray(batch.top_flags) ? batch.top_flags : [];
  return flags.map((f, i) => {
    const rawScore = f.fraud_composite_score ?? f.composite_score;
    const score = rawScore != null && rawScore !== '' ? Number(rawScore) : NaN;
    return {
      enterprise_id: String(f.enterprise_id || `flag-${i}`),
      display_label: (f.display_label as string) || undefined,
      display_name: (f.display_name as string) || undefined,
      industry_l1: (f.industry_l1 as string) || undefined,
      fraud_composite_score: Number.isFinite(score) ? score : undefined,
      fraud_risk_level: mapRiskLevel(f.fraud_risk_level ?? f.risk_level),
      scbm_mismatch_score: f.scbm_mismatch_score != null ? Number(f.scbm_mismatch_score) : undefined,
      red_invoice_score: f.red_invoice_score != null ? Number(f.red_invoice_score) : undefined,
      concentration_score: f.concentration_score != null ? Number(f.concentration_score) : undefined,
      fraud_signals: f.signals as Record<string, unknown> | undefined,
      pyod_score: f.pyod_score != null ? Number(f.pyod_score) : undefined,
    };
  });
}

export interface FraudBatchView {
  rows: FraudAnalysisItem[];
  sample_count: number;
  flagged_count: number;
  avg_composite: number | null;
}

export interface AuthenticityBatchView {
  rows: AuthenticityItem[];
  sample_count: number;
  suspicious_count: number;
  avg_authenticity_score: number | null;
}

/** 解析批次 KPI（用 sample_count/flagged_count/avg_*，禁止用 top_N 列表长度冒充全表）。 */
export function normalizeFraudBatch(res: unknown): FraudBatchView {
  const rows = normalizeFraudRows(res);
  if (Array.isArray(res) || !res || typeof res !== 'object') {
    return {
      rows,
      sample_count: 0,
      flagged_count: 0,
      avg_composite: null,
    };
  }
  const batch = res as FraudBatchResponse;
  const sample = Number(batch.sample_count);
  const flagged = Number(batch.flagged_count);
  const avg = batch.avg_composite != null ? Number(batch.avg_composite) : NaN;
  return {
    rows,
    sample_count: Number.isFinite(sample) ? sample : 0,
    flagged_count: Number.isFinite(flagged) ? flagged : 0,
    avg_composite: Number.isFinite(avg) ? avg : null,
  };
}

/** 将 /risk/authenticity 批次响应当成表格行（top_suspicious）。 */
export function normalizeAuthenticityRows(res: unknown): AuthenticityItem[] {
  if (Array.isArray(res)) return res as AuthenticityItem[];
  if (!res || typeof res !== 'object') return [];
  const batch = res as AuthenticityBatchResponse;
  const rows = Array.isArray(batch.top_suspicious) ? batch.top_suspicious : [];
  return rows.map((r, i) => ({
    enterprise_id: String(r.enterprise_id || `susp-${i}`),
    display_label: (r.display_label as string) || undefined,
    display_name: (r.display_name as string) || undefined,
    industry_l1: (r.industry_l1 as string) || undefined,
    authenticity_score: r.authenticity_score != null ? Number(r.authenticity_score) : undefined,
    cross_avg_deviation:
      r.cross_avg_deviation != null
        ? Number(r.cross_avg_deviation)
        : r.avg_deviation != null
          ? Number(r.avg_deviation)
          : undefined,
    cross_suspicious:
      typeof r.cross_suspicious === 'boolean'
        ? r.cross_suspicious
        : undefined, // 缺失弃权，禁止默认 true 反向误报
  }));
}

export function normalizeAuthenticityBatch(res: unknown): AuthenticityBatchView {
  const rows = normalizeAuthenticityRows(res);
  if (Array.isArray(res) || !res || typeof res !== 'object') {
    return {
      rows,
      sample_count: 0,
      suspicious_count: 0,
      avg_authenticity_score: null,
    };
  }
  const batch = res as AuthenticityBatchResponse;
  const sample = Number(batch.sample_count);
  const susp = Number(batch.suspicious_count);
  const avg = batch.avg_authenticity_score != null ? Number(batch.avg_authenticity_score) : NaN;
  return {
    rows,
    sample_count: Number.isFinite(sample) ? sample : 0,
    suspicious_count: Number.isFinite(susp) ? susp : 0,
    avg_authenticity_score: Number.isFinite(avg) ? avg : null,
  };
}

/** 行业大类（含样本计数），供报告向导范围选择 */
export interface IndustryItem {
  industry_l1: string;
  n: number;
}

/** 单企业通道可选项（「企业N」可读名 + 行业/地区） */
export interface EnterpriseOption {
  enterprise_id: string;
  display_name: string;
  industry_l1: string;
  province: string;
}

export const riskApi = {
  /** Dashboard KPI + 风险等级分布 */
  getSummary: (): Promise<Record<string, unknown>> =>
    client.get('/risk/summary'),

  /** 行业大类列表（含样本计数） */
  getIndustries: async (): Promise<IndustryItem[]> => {
    const res = (await client.get('/risk/industries')) as { items?: IndustryItem[] };
    return Array.isArray(res?.items) ? res.items : [];
  },

  /** 企业清单（「企业N」可读名 + 行业/地区），供报告向导「指定企业」选择 */
  getEnterprises: async (q?: string): Promise<EnterpriseOption[]> => {
    const qs = q ? `?q=${encodeURIComponent(q)}` : '';
    const res = (await client.get(`/risk/enterprises${qs}`)) as { items?: EnterpriseOption[] };
    return Array.isArray(res?.items) ? res.items : [];
  },

  /** 预警清单 */
  getWarnings: (): Promise<WarningItem[] | { warnings: WarningItem[] }> =>
    client.get('/risk/warnings'),

  /** 单企业画像（六维评分 + 同业基准 + 发票/税务画像） */
  getEnterpriseProfile: (enterpriseId: string): Promise<EnterpriseProfileResponse> =>
    client.get(`/risk/enterprise/${enterpriseId}`),

  /** 反欺诈分析（行 + 批次元数据 KPI） */
  getFraud: async (industry?: string, limit = 40): Promise<FraudBatchView> => {
    const params = new URLSearchParams();
    if (industry) params.set('industry', industry);
    params.set('limit', String(limit));
    const raw = await client.get(`/risk/fraud?${params.toString()}`);
    return normalizeFraudBatch(raw);
  },

  /** 经营真实性分析 */
  getAuthenticity: async (industry?: string): Promise<AuthenticityBatchView> => {
    const params = new URLSearchParams();
    if (industry) params.set('industry', industry);
    const qs = params.toString();
    const raw = await client.get(`/risk/authenticity${qs ? `?${qs}` : ''}`);
    return normalizeAuthenticityBatch(raw);
  },

  /** 演示样机数据（仅显式 mock 模式调用，live 页禁止静默回落） */
  getMockSample: (): Promise<Record<string, unknown>> =>
    client.get('/risk/mock/sample'),

  getFraudDemo: (): Promise<Record<string, unknown>> =>
    client.get('/risk/fraud/demo'),

  getAuthenticityDemo: (): Promise<Record<string, unknown>> =>
    client.get('/risk/authenticity/demo'),
};

/** 指标字典 API */
export const metricsApi = {
  getDictionary: (): Promise<MetricDictionaryResponse> =>
    client.get('/metrics/dictionary'),
};

/** 数据接入 API */
export const ingestApi = {
  mapColumns: (columns: string[], useLlm = true): Promise<Record<string, unknown>> =>
    client.post('/ingest/map', { columns, use_llm: useLlm }),

  commit: (mappings: { source_column: string; target_field: string | null }[], mode = 'temporary', sessionId?: string): Promise<Record<string, unknown>> =>
    client.post('/ingest/commit', { mappings, mode, session_id: sessionId }),

  ingestRows: (params: {
    session_id?: string;
    identity_field?: string;
    mappings: { source_column: string; target_field: string | null }[];
    rows: Record<string, unknown>[];
    mode?: string;
  }): Promise<Record<string, unknown>> =>
    client.post('/ingest/rows', params),
};
