import client from './client';
import type {
  ChartConfig,
  ChatAction,
  GuidanceCard,
  ChatReportMeta,
  FollowUpItem,
  ProcessStep,
} from '@/types/chat';

/** 后端 Chat 请求体 */
export interface ChatRequest {
  query: string;
  session_id?: string;
  enterprise_id?: string;
  followup?: FollowUpItem;
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
    followup_items?: FollowUpItem[];
    actions?: ChatAction[];
    guidance_cards?: GuidanceCard[];
    [key: string]: unknown;
  };
  charts?: unknown;
  visuals?: unknown;
  process?: ProcessStep[];
  // 后端可能附加的其他字段（由 route_chat 动态返回）
  [key: string]: unknown;
}

/** 对话范围状态（后端真源） */
export interface DialogueState {
  scope: 'unbound' | 'individual' | 'cohort' | string;
  subject?: { enterprise_id?: string; display_name?: string } | null;
  scenario?: string | null;
}

export interface ChatUiBundle {
  welcome?: string;
  chips?: FollowUpItem[];
  scope_bar?: {
    label?: string;
    scope?: string;
    enterprise_id?: string;
    display_name?: string;
    hint?: string;
  };
  scenario_buttons?: Array<{
    id: string;
    label: string;
    question?: string;
    hint?: string;
    action?: string;
  }>;
}

export interface ChatBootstrapResponse {
  session_id: string;
  dialogue_state: DialogueState;
  ui: ChatUiBundle;
}

/** 前端 Chat 响应（统一格式） */
export interface ChatResponse {
  conclusion: string;
  session_id?: string;
  evidence: EvidenceItem[];
  trace: string;
  followups: string[];
  followupItems?: FollowUpItem[];
  actions?: ChatAction[];
  guidanceCards?: GuidanceCard[];
  function?: string;
  dimension?: string;
  chart?: ChartConfig;
  visuals?: ChartConfig[];
  replySource?: string;
  analysisMode?: string;
  parseSource?: string;
  report?: ChatReportMeta;
  processSteps?: ProcessStep[];
  dialogueState?: DialogueState | null;
  ui?: ChatUiBundle | null;
  enterprise_id?: string;
  semanticPlanSummary?: string;
  semanticPlannerStatus?: string;
  semanticPlannerErrors?: string[];
  semanticCompositionToolIds?: string[];
  reportPlanId?: string;
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
  bootstrap: async (sessionId?: string): Promise<ChatBootstrapResponse> => {
    const suffix = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
    return (await client.get(`/chat/bootstrap${suffix}`)) as ChatBootstrapResponse;
  },

  send: async (
    params: ChatRequest,
    onProgress?: (step: ProcessStep) => void
  ): Promise<ChatResponse> => {
    let res: ChatBackendResponse;
    if (onProgress) {
      res = await sendStreamingChat(params, onProgress);
    } else {
      res = await client.post('/chat', params);
    }
    return normalizeBackendResponse(res);
  },

  listSessions: async (): Promise<ChatSessionSummary[]> => {
    const res = (await client.get('/chat/sessions')) as { sessions?: ChatSessionSummary[] };
    return Array.isArray(res?.sessions) ? res.sessions : [];
  },

  getSession: async (sessionId: string): Promise<ChatSessionDetail> => {
    return (await client.get(`/chat/sessions/${encodeURIComponent(sessionId)}`)) as ChatSessionDetail;
  },

  deleteSession: async (sessionId: string): Promise<void> => {
    await client.delete(`/chat/sessions/${encodeURIComponent(sessionId)}`);
  },
};

function baseUrl(): string {
  return '/api/v1';
}

async function sendStreamingChat(
  params: ChatRequest,
  onProgress: (step: ProcessStep) => void
): Promise<ChatBackendResponse> {
  const token = localStorage.getItem('access_token');
  const response = await fetch(`${baseUrl()}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(params),
  });
  if (!response.ok || !response.body) {
    throw { response: { status: response.status } };
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalPayload: ChatBackendResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSseBlock(block);
      if (parsed?.event === 'progress') {
        onProgress(parsed.data as ProcessStep);
      } else if (parsed?.event === 'result') {
        finalPayload = parsed.data as ChatBackendResponse;
      } else if (parsed?.event === 'error') {
        throw { response: { status: 503, data: parsed.data } };
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
  if (!finalPayload) {
    throw { response: { status: 503 } };
  }
  return finalPayload;
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  const eventLine = block.split('\n').find((line) => line.startsWith('event:'));
  const dataLine = block.split('\n').find((line) => line.startsWith('data:'));
  if (!eventLine || !dataLine) return null;
  try {
    return {
      event: eventLine.slice('event:'.length).trim(),
      data: JSON.parse(dataLine.slice('data:'.length).trim()),
    };
  } catch {
    return null;
  }
}

function normalizeBackendResponse(res: ChatBackendResponse): ChatResponse {
    const backendData = res.data;
    const followupItems = Array.isArray(backendData?.followup_items)
      ? (backendData.followup_items as FollowUpItem[])
      : [];
    const followups =
      followupItems.length > 0
        ? followupItems.map((x) => x.label).filter(Boolean)
        : backendData?.followups || [];
    const actions = Array.isArray(backendData?.actions) ? backendData.actions : [];
    const guidanceCards = Array.isArray(backendData?.guidance_cards)
      ? (backendData.guidance_cards as GuidanceCard[])
      : [];
    const evidence = claimsToEvidence(backendData?.claims);
    const primary = (backendData?.primary || {}) as Record<string, unknown>;
    const reportPlan = (backendData?.report_plan || {}) as Record<string, unknown>;

    return {
      conclusion: res.reply || '',
      session_id: res.session_id,
      evidence,
      trace: res.intent || '',
      followups,
      followupItems,
      actions,
      guidanceCards,
      function: res.function,
      dimension: res.dimension,
      chart: normalizeChart(res.charts),
      visuals: Array.isArray(res.visuals)
        ? res.visuals.map(normalizeChart).filter((item): item is ChartConfig => Boolean(item))
        : (() => {
            const chart = normalizeChart(res.charts);
            return chart ? [chart] : [];
          })(),
      replySource: res.reply_source || res.judgment_modes?.narration,
      analysisMode: res.analysis_mode || res.judgment_modes?.analysis || 'rule',
      parseSource: res.parse_source || res.judgment_modes?.parse,
      report: (backendData?.report as ChatReportMeta | undefined) || undefined,
      processSteps: Array.isArray(res.process) ? res.process : [],
      dialogueState:
        (res.dialogue_state as DialogueState | undefined) ||
        (backendData?.dialogue_state as DialogueState | undefined) ||
        null,
      ui:
        (res.ui as ChatUiBundle | undefined) ||
        (backendData?.ui as ChatUiBundle | undefined) ||
        null,
      enterprise_id: (res.enterprise_id as string | undefined) || undefined,
      semanticPlanSummary: typeof primary.semantic_plan_summary === 'string'
        ? primary.semantic_plan_summary
        : undefined,
      semanticPlannerStatus: typeof primary.semantic_planner_status === 'string'
        ? primary.semantic_planner_status
        : undefined,
      semanticPlannerErrors: Array.isArray(primary.semantic_planner_errors)
        ? primary.semantic_planner_errors.map(String)
        : [],
      semanticCompositionToolIds: Array.isArray(primary.semantic_composition_tool_ids)
        ? primary.semantic_composition_tool_ids.map(String)
        : [],
      reportPlanId: typeof reportPlan.plan_id === 'string' ? reportPlan.plan_id : undefined,
    };
}

/** 会话列表项（M0） */
export interface ChatSessionSummary {
  session_id: string;
  summary: string;
  updated_at: string;
  message_count?: number;
}

/** 会话详情（含可回填 messages） */
export interface ChatSessionDetail {
  session_id: string;
  owner?: string;
  history?: unknown[];
  messages?: Array<{
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: number;
    followups?: string[];
  }>;
  updated_at?: string;
  last_function?: string | null;
  last_dimension?: string | null;
  enterprise_id?: string | null;
  covered_functions?: string[];
}
