/** 报告场景/模块（与后端 report_templates.SCENARIOS 对齐：全量/行业 = 画像 + 预警） */
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

/** 全量 / 行业：仅两主题 */
export const PORTFOLIO_SCENARIOS: ReportScenarioDef[] = [
  {
    key: 'portrait',
    label: '样本库画像',
    title: '样本库画像报告',
    subtitle: '结构分布 · 均值分布 · 信用与规模画像',
    tier: 'general',
    description: '监管/机构组合视角：刻画样本结构与分布，不作单户定性。',
    dataFocus: ['企业基础信息', '财务数据', '税务数据'],
    motif: 'badge',
    accent: '#6d28d9',
    chapters: ['地区信用结构', '行业规模与趋势', '行业基准定位', '六维经营表现画像'],
    audience: 'portfolio',
  },
  {
    key: 'alert',
    label: '风险预警',
    title: '风险预警报告',
    subtitle: '预警阈值 · 命中家数 · 信号分布（匿名）',
    tier: 'general',
    description: '监管/稽查预警：阈值、匿名命中家数与信号分布（不含具名名单）。',
    dataFocus: ['税务数据', '发票数据', '财务数据', '企业基础信息'],
    motif: 'magnifier',
    accent: '#d32f2f',
    chapters: ['预警信号总览', '发票异常预警', '税务合规预警', '真实性交叉预警'],
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
  accent: '#003366',
  chapters: ['评级摘要', '六维风险分析', '财务能力明细', '主要财务数据'],
  audience: 'enterprise',
};
