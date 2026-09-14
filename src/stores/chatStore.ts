import { create } from 'zustand';
import type { Message, ChatContext, DimensionType, FunctionType, FollowUpItem } from '@/types/chat';
import { chatApi, type ChatSessionSummary, type DialogueState, type ChatUiBundle } from '@/api/chat';
import { uid } from '@/utils/formatters';

interface ChatStore {
  messages: Message[];
  context: ChatContext;
  isLoading: boolean;
  sessionId: string | null;
  enterpriseId: string | null;
  sessions: ChatSessionSummary[];
  sessionsLoading: boolean;
  restored: boolean;
  ingestModalOpen: boolean;
  dialogueState: DialogueState | null;
  ui: ChatUiBundle | null;

  sendMessage: (text: string, followup?: FollowUpItem) => Promise<void>;
  selectDimension: (dim: DimensionType) => void;
  selectFunction: (func: FunctionType) => void;
  clickFollowUp: (question: string | FollowUpItem) => void;
  clearChat: () => void;
  addUserMessage: (text: string) => void;
  setEnterpriseId: (id: string | null) => void;
  openIngestModal: () => void;
  closeIngestModal: () => void;
  bootstrapSession: () => Promise<void>;
  restoreHistory: () => Promise<void>;
  loadSession: (sessionId: string) => Promise<void>;
  refreshSessions: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  resetLocalChat: () => void;
}

const initialContext: ChatContext = {
  currentDimension: null,
  currentFunction: null,
  coveredFunctions: [],
  lastConclusion: null,
};

function sessionStorageKey(email: string | null | undefined): string | null {
  const e = (email || localStorage.getItem('userEmail') || '').trim().toLowerCase();
  if (!e) return null;
  return `chat_session_${e}`;
}

function readPersistedSessionId(): string | null {
  const key = sessionStorageKey(null);
  if (!key) return null;
  return localStorage.getItem(key);
}

function writePersistedSessionId(sessionId: string | null) {
  const key = sessionStorageKey(null);
  if (!key) return;
  if (sessionId) localStorage.setItem(key, sessionId);
  else localStorage.removeItem(key);
}

export function clearChatLocalCache(email?: string | null) {
  const specific = sessionStorageKey(email);
  if (specific) {
    localStorage.removeItem(specific);
    return;
  }
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i += 1) {
    const k = localStorage.key(i);
    if (k && k.startsWith('chat_session_')) keys.push(k);
  }
  keys.forEach((k) => localStorage.removeItem(k));
}

const createWelcomeMessage = (ui?: ChatUiBundle | null): Message => ({
  id: 'welcome',
  role: 'assistant',
  content:
    ui?.welcome ||
    '我是明鉴风控顾问。先选分析范围：试用演示企业、从列表选一家，或看全库群体。范围不清时我不会用全样本冒充「这家」。',
  timestamp: Date.now(),
  followups: (ui?.chips || []).map((c) => c.label).filter(Boolean),
  followupItems: ui?.chips || [
    { type: 'switch_scope', label: '试用演示企业', target: 'individual', params: { use_demo: true } },
    { type: 'switch_scope', label: '从列表选一家', target: 'individual', params: { open_picker: true } },
    { type: 'switch_scope', label: '看全库 193 家群体', target: 'cohort' },
  ],
});

function errorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  const code = (error as { code?: string })?.code;
  if (status === 429) return '请求过于频繁，请稍后再试。';
  if (status === 503) return '服务暂时不可用，请稍后重试。';
  if (status === 500) return '服务内部错误，请稍后重试。';
  if (status === 401) return '登录已过期，请重新登录。';
  if (code === 'ECONNABORTED') return '请求超时，请检查网络后重试。';
  return '抱歉，服务暂时不可用，请稍后重试。';
}

function applyDialogueFromRes(
  set: (
    partial: Partial<ChatStore> | ((s: ChatStore) => Partial<ChatStore>)
  ) => void,
  res: {
    dialogueState?: DialogueState | null;
    ui?: ChatUiBundle | null;
    enterprise_id?: string;
  }
) {
  const ds = res.dialogueState;
  let eid: string | null | undefined;
  if (ds?.scope === 'individual') {
    eid = ds.subject?.enterprise_id || res.enterprise_id || null;
  } else if (ds?.scope === 'cohort' || ds?.scope === 'unbound') {
    eid = null;
  }
  set((s) => ({
    dialogueState: ds ?? s.dialogueState,
    ui: res.ui ?? s.ui,
    ...(eid !== undefined ? { enterpriseId: eid } : {}),
  }));
}

const useChatStore = create<ChatStore>((set, get) => ({
  messages: [createWelcomeMessage()],
  context: { ...initialContext },
  isLoading: false,
  sessionId: readPersistedSessionId(),
  enterpriseId: null,
  sessions: [],
  sessionsLoading: false,
  restored: false,
  ingestModalOpen: false,
  dialogueState: { scope: 'unbound', subject: null, scenario: null },
  ui: null,

  setEnterpriseId: (id: string | null) => {
    if (id === get().enterpriseId) return;
    set({ enterpriseId: id });
  },

  openIngestModal: () => set({ ingestModalOpen: true }),
  closeIngestModal: () => set({ ingestModalOpen: false }),

  addUserMessage: (text: string) => {
    set((s) => ({
      messages: [
        ...s.messages,
        { id: uid(), role: 'user', content: text, timestamp: Date.now() },
      ],
    }));
  },

  bootstrapSession: async () => {
    const { sessionId } = get();
    try {
      const res = await chatApi.send({
        query: '',
        session_id: sessionId || undefined,
        followup: { type: 'bootstrap', label: 'bootstrap' },
      });
      const nextSessionId = res.session_id || sessionId;
      if (nextSessionId) writePersistedSessionId(nextSessionId);
      applyDialogueFromRes(set, res);
      set({
        sessionId: nextSessionId,
        messages: [createWelcomeMessage(res.ui)],
      });
    } catch {
      /* keep local unbound welcome */
    }
  },

  sendMessage: async (text: string, followup?: FollowUpItem) => {
    const { context, addUserMessage, sessionId, enterpriseId, dialogueState } = get();
    if (followup?.type === 'switch_scope' && followup.label) {
      addUserMessage(followup.label);
    } else if ((text || '').trim()) {
      addUserMessage(text);
    }
    set({ isLoading: true });

    try {
      const sendEid =
        dialogueState?.scope === 'individual'
          ? enterpriseId || dialogueState.subject?.enterprise_id || undefined
          : followup?.type === 'switch_scope' && followup.params?.enterprise_id
            ? String(followup.params.enterprise_id)
            : undefined;

      const res = await chatApi.send({
        query: text || followup?.label || '',
        session_id: sessionId || undefined,
        enterprise_id: sendEid,
        followup,
      });

      applyDialogueFromRes(set, res);

      const aiMsg: Message = {
        id: uid(),
        role: 'assistant',
        content: res.conclusion,
        timestamp: Date.now(),
        chart: res.chart,
        followups: res.followups,
        followupItems: res.followupItems?.length ? res.followupItems : res.ui?.chips,
        actions: res.actions,
        guidanceCards: res.guidanceCards,
        evidence: res.evidence,
        evidence_chain: res.evidence.map((e) => e.content),
        trace: res.trace,
        replySource: res.replySource,
        analysisMode: res.analysisMode || 'rule',
        parseSource: res.parseSource,
        report: res.report,
      };

      const nextSessionId = res.session_id || sessionId;
      if (nextSessionId) writePersistedSessionId(nextSessionId);

      set((s) => ({
        messages: [...s.messages, aiMsg],
        isLoading: false,
        sessionId: nextSessionId,
        context: {
          ...s.context,
          lastConclusion: res.conclusion,
          currentFunction: (res.function as FunctionType) ?? s.context.currentFunction,
          currentDimension: (res.dimension as DimensionType) ?? s.context.currentDimension,
          coveredFunctions: context.currentFunction
            ? [...new Set([...s.context.coveredFunctions, context.currentFunction])]
            : s.context.coveredFunctions,
        },
      }));
      void get().refreshSessions();
    } catch (error) {
      set((s) => ({
        messages: [
          ...s.messages,
          {
            id: uid(),
            role: 'assistant',
            content: errorMessage(error),
            timestamp: Date.now(),
            followups: ['重新提问', '查看整体概览'],
          },
        ],
        isLoading: false,
      }));
    }
  },

  selectDimension: (dim) => {
    set((s) => ({ context: { ...s.context, currentDimension: dim } }));
  },

  selectFunction: (func) => {
    set((s) => ({ context: { ...s.context, currentFunction: func } }));
  },

  clickFollowUp: (question) => {
    if (typeof question === 'string') {
      // 正文拼句误触：按分号拆开提示用户用按钮（后端也会拦）
      get().sendMessage(question);
      return;
    }
    const item = question;
    if (item.type === 'navigate') return;
    if (
      item.type === 'switch_scope' ||
      item.type === 'drilldown' ||
      item.type === 'action' ||
      item.type === 'dialog_act' ||
      item.type === 'query'
    ) {
      // query 也可能带 params；一律带上结构化 followup，禁止只发裸文案
      void get().sendMessage(item.label || '继续', item);
      return;
    }
    get().sendMessage(item.label);
  },

  clearChat: () => {
    writePersistedSessionId(null);
    set({
      messages: [createWelcomeMessage()],
      context: { ...initialContext },
      sessionId: null,
      enterpriseId: null,
      dialogueState: { scope: 'unbound', subject: null, scenario: null },
      ui: null,
    });
    void get().bootstrapSession();
  },

  resetLocalChat: () => {
    writePersistedSessionId(null);
    set({
      messages: [createWelcomeMessage()],
      context: { ...initialContext },
      sessionId: null,
      enterpriseId: null,
      sessions: [],
      restored: false,
      dialogueState: { scope: 'unbound', subject: null, scenario: null },
      ui: null,
    });
  },

  refreshSessions: async () => {
    if (!localStorage.getItem('access_token')) {
      set({ sessions: [] });
      return;
    }
    set({ sessionsLoading: true });
    try {
      const sessions = await chatApi.listSessions();
      set({ sessions, sessionsLoading: false });
    } catch {
      set({ sessionsLoading: false });
    }
  },

  restoreHistory: async () => {
    if (!localStorage.getItem('access_token')) {
      set({ restored: true });
      return;
    }
    set({ sessionsLoading: true });
    try {
      const sessions = await chatApi.listSessions();
      set({ sessions });
      const preferred = readPersistedSessionId();
      const target =
        (preferred && sessions.find((s) => s.session_id === preferred)?.session_id) ||
        sessions[0]?.session_id;
      if (!target) {
        set({ restored: true, sessionsLoading: false });
        await get().bootstrapSession();
        return;
      }
      await get().loadSession(target);
      set({ restored: true, sessionsLoading: false });
      try {
        const res = await chatApi.send({
          query: '',
          session_id: target,
          followup: { type: 'bootstrap', label: 'bootstrap' },
        });
        applyDialogueFromRes(set, res);
      } catch {
        /* ignore */
      }
    } catch {
      set({ restored: true, sessionsLoading: false });
    }
  },

  loadSession: async (sessionId: string) => {
    if (!sessionId) return;
    try {
      const detail = await chatApi.getSession(sessionId);
      const restoredMsgs: Message[] = Array.isArray(detail.messages)
        ? detail.messages
            .filter((m) => m && (m.role === 'user' || m.role === 'assistant') && m.content)
            .map((m) => ({
              id: m.id || uid(),
              role: m.role,
              content: m.content,
              timestamp: m.timestamp || Date.now(),
              followups: m.followups,
            }))
        : [];
      writePersistedSessionId(detail.session_id);
      set({
        sessionId: detail.session_id,
        enterpriseId: detail.enterprise_id || null,
        messages: restoredMsgs.length ? restoredMsgs : [createWelcomeMessage()],
      });
    } catch {
      /* ignore */
    }
  },

  deleteSession: async (sessionId: string) => {
    await chatApi.deleteSession(sessionId);
    if (get().sessionId === sessionId) get().clearChat();
    await get().refreshSessions();
  },
}));

export default useChatStore;
