/** 图表配置 */
export interface ChartConfig {
  type: string;
  title?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
}

/** 风控结论原子结构 */
export interface ConclusionAtom {
  conclusion: string;
  evidence_chain: string[];
  trace: string;
  followups: string[];
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

/** 消息类型 */
export type MessageRole = 'user' | 'assistant' | 'system';

/** 可点击的引导动作：跳转到具体功能页（报告向导 / 数据接入等） */
export interface ChatAction {
  label: string;
  target: string;
}

/** 强拦截引导卡片（方案 A）：定制报告无可用数据时给出可点击调整项 */
export interface GuidanceCard {
  label: string;
  description: string;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  /** AI 回复附带的图表 */
  chart?: ChartConfig;
  /** 追问建议 */
  followups?: string[];
  /** 引导动作（跳转功能页，区别于追问文本） */
  actions?: ChatAction[];
  /** 强拦截引导卡片（方案 A）：无可用数据时的结构化调整项 */
  guidanceCards?: GuidanceCard[];
  /** 证据链（仅报告使用，对话中隐藏） */
  evidence_chain?: string[];
  /** 结构化溯源证据 */
  evidence?: EvidenceItem[];
  /** 溯源 */
  trace?: string;
  /** 表述来源：llm | template */
  replySource?: 'llm' | 'template' | string;
  /** 数字/风险研判来源：rule（当前恒规则） */
  analysisMode?: 'rule' | 'llm' | string;
  /** 意图解析来源：rule | llm | corrected */
  parseSource?: string;
}

/** 对话上下文 */
export interface ChatContext {
  currentDimension: string | null;
  currentFunction: string | null;
  coveredFunctions: string[];
  lastConclusion: string | null;
}

/** 维度类型 */
export type DimensionType = 'overall' | 'industry' | 'region' | 'time' | 'signal';

/** 功能类型 */
export type FunctionType = 'score' | 'authenticity' | 'fraud' | 'benchmark' | 'trend';

/** 维度卡配置 */
export interface DimensionItem {
  id: DimensionType;
  label: string;
  icon: string;
  prefix: string;
}

/** 功能卡配置 */
export interface FunctionItem {
  id: FunctionType;
  label: string;
  description: string;
  icon: string;
  suffix: string;
}

/** 组合卡配置 */
export interface ComboItem {
  id: string;
  dimension: string;
  function: string;
  label: string;
  icon?: string;
}
