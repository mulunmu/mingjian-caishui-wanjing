import client from './client';
import type { ChartConfig, ChatAction, GuidanceCard } from '@/types/chat';

/** 后端 Chat 请求体 */
export interface ChatRequest {
  query: string;
  session_id?: string;
  enterprise_id?: string;
}

/** 后端 claim trace 结构 */
interface ClaimTrace {
  table?: string;
  field?: string;
  query_id?: string;
}

/** 后端 claim 结构 */
interface BackendClaim {
  claim?: string;
  trace?: ClaimTrace;
  confidence?: string;
  evidence_chain?: string[];
  value?: {
    metric?: string;
    number?: number | null;
    unit?: string;
  };
}

/** 溯源证据项 */
export interface EvidenceItem {
  /** 结论内容 */
  content: string;
  /** 数据来源描述 */
  source: string;
  /** 置信度 */
  confidence?: string;
  /** 证据链 */
  evidence_chain?: string[];
}

/** 后端 Chat 响应 */
export interface ChatBackendResponse {
  reply: string;
  reply_source?: string;
  analysis_mode?: string;
  parse_source?: string;
  judgment_modes?: {
    analysis?: string;
    parse?: string;
    narration?: string;
  };
  session_id?: string;
  session_note?: string;
  intent?: string;
  function?: string;
  dimension?: string;
  data?: {
    claims?: BackendClaim[];
    followups?: string[];
    actions?: ChatAction[];
    guidance_cards?: GuidanceCard[];
    [key: string]: unknown;
  };
  charts?: unknown;
  // 后端可能附加的其他字段（由 route_chat 动态返回）
  [key: string]: unknown;
}

/** 前端 Chat 响应（统一格式） */
export interface ChatResponse {
  conclusion: string;
  session_id?: string;
  evidence: EvidenceItem[];
  trace: string;
  followups: string[];
  actions?: ChatAction[];
  guidanceCards?: GuidanceCard[];
  function?: string;
  dimension?: string;
  chart?: ChartConfig;
  replySource?: string;
  analysisMode?: string;
  parseSource?: string;
}

/** 将后端 claims 转换为前端 EvidenceItem 数组 */
function claimsToEvidence(claims: BackendClaim[] | undefined): EvidenceItem[] {
  if (!Array.isArray(claims)) return [];
  return claims
    .filter((c) => c.claim) // 过滤空 claim
    .map((c) => ({
      content: c.claim || '',
      source: c.trace?.table
        ? `${c.trace.table}${c.trace.field ? '.' + c.trace.field : ''}${c.trace.query_id ? ' (' + c.trace.query_id + ')' : ''}`
        : '评估引擎',
      confidence: c.confidence,
      evidence_chain: c.evidence_chain,
    }));
}

/**
 * 后端图表 payload → 前端图表组件数据格式适配。
 * 后端统一为 {type, data:{labels, series:[{name, values}]}}（雷达为 {indicators, values, name}），
 * 前端各组件期望的 shape 不一致，这里做归一化。
 */
function normalizeChart(chart: unknown): ChartConfig | undefined {
  if (!chart || typeof chart !== 'object') return undefined;
  const c = chart as { type?: unknown; data?: any };
  const type = typeof c.type === 'string' ? c.type : '';
  const d = c.data ?? {};
  const labels: string[] = Array.isArray(d.labels) ? d.labels : [];
  const series: { name: string; values: number[] }[] = Array.isArray(d.series)
    ? d.series
    : [];

  switch (type) {
    case 'bar':
      // 单系列 → 扁平 values；多系列 → series（BarChart 两者都支持）
      if (series.length === 1) {
        return {
          type: 'bar',
          data: { categories: labels, values: series[0].values, title: series[0].name },
        };
      }
      return { type: 'bar', data: { categories: labels, series } };
    case 'line':
      return { type: 'line', data: { categories: labels, series } };
    case 'pie':
      return {
        type: 'pie',
        data: labels.map((name, i) => ({ name, value: series[0]?.values[i] ?? 0 })),
      };
    case 'radar':
      return {
        type: 'radar',
        data: { indicators: d.indicators ?? [], values: d.values ?? [], title: d.name },
      };
    case 'heatmap':
      return {
        type: 'heatmap',
        data: {
          xLabels: d.xLabels ?? d.x_labels ?? [],
          yLabels: d.yLabels ?? d.y_labels ?? [],
          values: d.values ?? [],
          title: d.title,
        },
      };
    case 'funnel':
      // 无专用漏斗组件时降级为水平条形，避免静默丢图
      return {
        type: 'bar',
        data: {
          categories: labels.length ? labels : (Array.isArray(d.labels) ? d.labels : []),
          values: Array.isArray(d.values)
            ? d.values
            : series[0]?.values ?? [],
          title: '风险筛查漏斗',
        },
      };
    case 'scatter':
      return {
        type: 'scatter',
        data: d,
      };
    default:
      return undefined;
  }
}

export const chatApi = {
  send: async (params: ChatRequest): Promise<ChatResponse> => {
    const res: ChatBackendResponse = await client.post('/chat', params);

    // 适配层：后端 reply → 前端 conclusion
    // 从后端 data 中提取 followups 和 claims（后端结构: res.data.followups / res.data.claims）
    const backendData = res.data;
    const followups = backendData?.followups || [];
    const actions = Array.isArray(backendData?.actions) ? backendData.actions : [];
    const guidanceCards = Array.isArray(backendData?.guidance_cards)
      ? (backendData.guidance_cards as GuidanceCard[])
      : [];
    const evidence = claimsToEvidence(backendData?.claims);

    return {
      conclusion: res.reply || '',
      session_id: res.session_id,
      evidence,
      trace: res.intent || '',
      followups,
      actions,
      guidanceCards,
      function: res.function,
      dimension: res.dimension,
      chart: normalizeChart(res.charts),
      replySource: res.reply_source || res.judgment_modes?.narration,
      analysisMode: res.analysis_mode || res.judgment_modes?.analysis || 'rule',
      parseSource: res.parse_source || res.judgment_modes?.parse,
    };
  },
};
