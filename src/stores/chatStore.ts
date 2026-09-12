import { create } from 'zustand';
import type { Message, ChatContext, DimensionType, FunctionType } from '@/types/chat';
import { chatApi } from '@/api/chat';
import { uid } from '@/utils/formatters';

interface ChatStore {
  messages: Message[];
  context: ChatContext;
  isLoading: boolean;
  sessionId: string | null;
  enterpriseId: string | null;

  // actions
  sendMessage: (text: string) => Promise<void>;
  selectDimension: (dim: DimensionType) => void;
  selectFunction: (func: FunctionType) => void;
  clickFollowUp: (question: string) => void;
  clearChat: () => void;
  addUserMessage: (text: string) => void;
  setEnterpriseId: (id: string | null) => void;
}

const initialContext: ChatContext = {
  currentDimension: null,
  currentFunction: null,
  coveredFunctions: [],
  lastConclusion: null,
};

// 欢迎消息：每次调用重新生成时间戳，避免长时间打开页面时时间失真（BUG-07）
const createWelcomeMessage = (): Message => ({
  id: 'welcome',
  role: 'assistant',
  content:
    '你好！我是明鉴风控引擎，专注财税票风险分析。你可以通过右侧卡片选择分析维度和功能（评分、真实性、反欺诈、基准、趋势），或直接输入问题，我会基于已接入的匿名企业数据给出可溯源的分析结论。',
  timestamp: Date.now(),
  followups: [
    '整体风险评分如何？',
    '哪些行业风险评分最高？',
    '经营真实性验证结果',
  ],
});

// 按错误类型给出可读提示：不回显用户输入、不泄露技术实现细节（BUG-02/03）
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

const useChatStore = create<ChatStore>((set, get) => ({
  messages: [createWelcomeMessage()],
  context: { ...initialContext },
  isLoading: false,
  sessionId: null,
  enterpriseId: null,

  setEnterpriseId: (id: string | null) => {
    // 切换主体只换锚点，不清空对话（防中断）；「清空对话」按钮才是唯一重置入口。
    // 跨主体不串味靠后端按 enterprise_id 接地，而非前端清空历史。
    if (id === get().enterpriseId) return;
    set({ enterpriseId: id });
  },

  addUserMessage: (text: string) => {
    const userMsg: Message = {
      id: uid(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    set((s) => ({ messages: [...s.messages, userMsg] }));
  },

  sendMessage: async (text: string) => {
    const { context, addUserMessage, sessionId, enterpriseId } = get();
    addUserMessage(text);
    set({ isLoading: true });

    try {
      const res = await chatApi.send({
        query: text,
        session_id: sessionId || undefined,
        enterprise_id: enterpriseId || undefined,
      });

      const aiMsg: Message = {
        id: uid(),
        role: 'assistant',
        content: res.conclusion,
        timestamp: Date.now(),
        chart: res.chart,
        followups: res.followups,
        actions: res.actions,
        guidanceCards: res.guidanceCards,
        evidence: res.evidence,
        evidence_chain: res.evidence.map((e) => e.content),
        trace: res.trace,
        replySource: res.replySource,
        analysisMode: res.analysisMode || 'rule',
        parseSource: res.parseSource,
      };

      set((s) => ({
        messages: [...s.messages, aiMsg],
        isLoading: false,
        // 保存 session_id 用于上下文记忆
        sessionId: res.session_id || s.sessionId,
        context: {
          ...s.context,
          lastConclusion: res.conclusion,
          // 用后端实际解析出的 function/dimension 同步前端 context，避免手动输入与卡片选中态不一致（BUG-10）
          currentFunction: res.function ?? s.context.currentFunction,
          currentDimension: res.dimension ?? s.context.currentDimension,
          coveredFunctions: context.currentFunction
            ? [...new Set([...s.context.coveredFunctions, context.currentFunction])]
            : s.context.coveredFunctions,
        },
      }));
    } catch (error) {
      const aiMsg: Message = {
        id: uid(),
        role: 'assistant',
        content: errorMessage(error),
        timestamp: Date.now(),
        followups: ['重新提问', '查看整体概览'],
      };
      set((s) => ({
        messages: [...s.messages, aiMsg],
        isLoading: false,
      }));
    }
  },

  selectDimension: (dim) => {
    set((s) => ({
      context: { ...s.context, currentDimension: dim },
    }));
  },

  selectFunction: (func) => {
    set((s) => ({
      context: { ...s.context, currentFunction: func },
    }));
  },

  clickFollowUp: (question) => {
    get().sendMessage(question);
  },

  clearChat: () => {
    set({
      messages: [createWelcomeMessage()],
      context: { ...initialContext },
      sessionId: null,
      enterpriseId: null,
    });
  },
}));

export default useChatStore;
