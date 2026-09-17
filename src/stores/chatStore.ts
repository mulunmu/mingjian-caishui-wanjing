import { create } from 'zustand';
import type { Message, ChatContext, DimensionType, FunctionType, FollowUpItem, ProcessStep } from '@/types/chat';
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
  activeProcess: ProcessStep[];
  pickerRequested: boolean;

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
  requestScopePicker: () => void;
  consumeScopePicker: () => void;
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

const createWelcomeMessage = (ui?: ChatUiBundle | null): Message | null => {
  if (!ui?.welcome) return null;
  return {
    id: 'welcome',
    role: 'assistant',
    content: ui.welcome,
    timestamp: Date.now(),
    followups: (ui.chips || []).map((c) => c.label).filter(Boolean),
    followupItems: ui.chips || [],
  };
};

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
  messages: [],
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
  activeProcess: [],
  pickerRequested: false,

  setEnterpriseId: (id: string | null) => {
    if (id === get().enterpriseId) return;
    set({ enterpriseId: id });
  },

  openIngestModal: () => set({ ingestModalOpen: true }),
  closeIngestModal: () => set({ ingestModalOpen: false }),
  requestScopePicker: () => set({ pickerRequested: true }),
  consumeScopePicker: () => set({ pickerRequested: false }),

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
    set({ isLoading: true });
    try {
      const res = await chatApi.bootstrap(sessionId || undefined);
      const nextSessionId = res.session_id || sessionId;
      if (nextSessionId) writePersistedSessionId(nextSessionId);
      set({
        dialogueState: res.dialogue_state,
        ui: res.ui,
        enterpriseId:
          res.dialogue_state?.scope === 'individual'
            ? res.dialogue_state.subject?.enterprise_id || null
            : null,
      });
      set({
        sessionId: nextSessionId,
        messages: createWelcomeMessage(res.ui) ? [createWelcomeMessage(res.ui)!] : [],
        isLoading: false,
      });
    } catch {
      set({ isLoading: false });
    }
  },

  sendMessage: async (text: string, followup?: FollowUpItem) => {
    const { context, addUserMessage, sessionId, enterpriseId, dialogueState } = get();
    if (followup?.type === 'switch_scope' && followup.label) {
      addUserMessage(followup.label);
    } else if ((text || '').trim()) {
      addUserMessage(text);
    }
    set({ isLoading: true, activeProcess: [] });

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
      }, (step) => {
        set((s) => ({ activeProcess: [...s.activeProcess, step] }));
      });

      applyDialogueFromRes(set, res);

      const aiMsg: Message = {
        id: uid(),
        role: 'assistant',
        content: res.conclusion,
        timestamp: Date.now(),
        chart: res.chart,
        visuals: res.visuals,
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
        processSteps: res.processSteps,
        semanticPlanSummary: res.semanticPlanSummary,
        semanticPlannerStatus: res.semanticPlannerStatus,
        semanticPlannerErrors: res.semanticPlannerErrors,
        semanticCompositionToolIds: res.semanticCompositionToolIds,
        reportPlanId: res.reportPlanId,
      };

      const nextSessionId = res.session_id || sessionId;
      if (nextSessionId) writePersistedSessionId(nextSessionId);

      set((s) => ({
        messages: [...s.messages, aiMsg],
        isLoading: false,
        activeProcess: [],
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
            followups: ['重新提问'],
          },
        ],
        isLoading: false,
        activeProcess: [],
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
      messages: [],
      isLoading: true,
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
      messages: [],
      isLoading: false,
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
        const res = await chatApi.bootstrap(target);
        set({
          dialogueState: res.dialogue_state,
          ui: res.ui,
          enterpriseId:
            res.dialogue_state?.scope === 'individual'
              ? res.dialogue_state.subject?.enterprise_id || null
              : null,
        });
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
        messages: restoredMsgs.length ? restoredMsgs : [],
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
