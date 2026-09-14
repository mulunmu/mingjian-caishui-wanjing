/** 报告场景/模块（与后端 report_templates.SCENARIOS 对齐：全量/行业 = 放贷/评级/预警/稽查） */
export type ScenarioMotif = 'ledger' | 'seal' | 'magnifier' | 'compass' | 'badge';

export interface ReportScenarioDef {
  key: string;
  /** 场景短名（卡片标题） */
  label: string;
  /** 报告标题（封面） */
  title: string;
  /** 封面副标题 */
  subtitle: string;
  tier: 'general' | 'premium';
  /** 场景定位（一句话） */
  description: string;
  /** 数据类侧重：财务/税务/发票/企业基础信息 */
  dataFocus: string[];
  /** 封面母题（前端据此渲染不同图形） */
  motif: ScenarioMotif;
  /** 场景主色 */
  accent: string;
  /** 章节名 */
  chapters: string[];
  /** 适用范围：组合视角（全库/行业）才展示；个体走企业体检路径 */
  audience: 'portfolio' | 'enterprise' | 'both';
}

/** 全量 / 行业：四业务场景 */
export const PORTFOLIO_SCENARIOS: ReportScenarioDef[] = [
  {
    key: 'loan',
    label: '放贷研判',
    title: '放贷研判报告',
    subtitle: '能不能贷 · 额度逻辑 · 附加条件',
    tier: 'general',
    description: '面向信贷：用经营与发票信号回答能不能贷、额度要不要收紧、附加条件写什么。',
    dataFocus: ['财务数据', '发票数据', '税务数据', '企业基础信息'],
    motif: 'compass',
    accent: '#3A6EA5',
    chapters: ['放贷综合判断', '发票与进销信号', '收入真实性', '同业对照与额度参考'],
    audience: 'portfolio',
  },
  {
    key: 'rating',
    label: '评级研判',
    title: '评级研判报告',
    subtitle: '信用结构 · 等级信号 · 六维经营表现',
    tier: 'general',
    description: '面向评级/授信：说明信用处在什么水平、结构强弱在哪。',
    dataFocus: ['企业基础信息', '财务数据', '税务数据'],
    motif: 'badge',
    accent: '#A18A5F',
    chapters: ['地区信用结构', '行业规模与趋势', '行业基准定位', '六维经营表现画像'],
    audience: 'portfolio',
  },
  {
    key: 'warn',
    label: '风险预警',
    title: '风险预警报告',
    subtitle: '预警阈值 · 命中家数 · 信号分布（匿名）',
    tier: 'general',
    description: '面向监测：阈值、匿名命中家数与信号分布（不含具名名单）。',
    dataFocus: ['税务数据', '发票数据', '财务数据', '企业基础信息'],
    motif: 'magnifier',
    accent: '#C87F1F',
    chapters: ['预警信号总览', '发票异常预警', '税务合规预警', '真实性交叉预警'],
    audience: 'portfolio',
  },
  {
    key: 'audit',
    label: '稽查线索',
    title: '稽查线索报告',
    subtitle: '可疑点 · 优先核查 · 可照做动作',
    tier: 'general',
    description: '面向稽查：指出哪里可疑、该先查什么，给出可照做的核查动作。',
    dataFocus: ['发票数据', '税务数据', '财务数据'],
    motif: 'seal',
    accent: '#A03C35',
    chapters: ['优先核查：发票异常', '优先核查：账票不一致', '税务合规疑点', '信号叠加与名单策略'],
    audience: 'portfolio',
  },
];

/** 向导场景列表（兼容旧引用名） */
export const REPORT_SCENARIOS: ReportScenarioDef[] = PORTFOLIO_SCENARIOS;

/** 个体范围不选场景卡，直接生成企业体检 */
export const ENTERPRISE_SCENARIO: ReportScenarioDef = {
  key: 'enterprise',
  label: '企业体检',
  title: '企业财务分析报告',
  subtitle: '六维体检 · 命中风险指标 · 建议',
  tier: 'general',
  description: '单户财税票健康体检（付费主路径）。',
  dataFocus: ['财务数据', '税务数据', '发票数据', '企业基础信息'],
  motif: 'compass',
  accent: '#152446',
  chapters: ['评级摘要', '六维风险分析', '财务能力明细', '主要财务数据'],
  audience: 'enterprise',
};
