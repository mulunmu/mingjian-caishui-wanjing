/** 报告场景/模块（与后端 report_templates.SCENARIOS 对齐） */
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
}

export const REPORT_SCENARIOS: ReportScenarioDef[] = [
  {
    key: 'financial',
    label: '财务健康体检',
    title: '财务健康体检报告',
    subtitle: '盈利能力 · 偿债能力 · 营运能力 · 现金流',
    tier: 'general',
    description: '以财务四大能力为主线，判断财务稳健度与偿债压力。',
    dataFocus: ['财务数据', '企业基础信息'],
    motif: 'ledger',
    accent: '#0f766e',
    chapters: ['财务四能力健康度', '财务勾稽与真实性', '财务同业对标', '营收趋势'],
  },
  {
    key: 'tax',
    label: '税务合规体检',
    title: '税务合规体检报告',
    subtitle: '税负水平 · 欠税风险 · 申报准时率',
    tier: 'general',
    description: '聚焦纳税准时率、税务违法信号与税负水平。',
    dataFocus: ['税务数据', '企业基础信息'],
    motif: 'seal',
    accent: '#1d4ed8',
    chapters: ['税务合规概览', '税务风险信号', '纳税信用与准时率', '税务-财报勾稽'],
  },
  {
    key: 'fraud',
    label: '发票舞弊排查',
    title: '发票舞弊排查报告',
    subtitle: '进销错配 · 红冲异常 · 集中度风险',
    tier: 'general',
    description: '覆盖进销错配、红字发票、集中度与序列缺口。',
    dataFocus: ['发票数据', '企业基础信息'],
    motif: 'magnifier',
    accent: '#d32f2f',
    chapters: ['发票舞弊切片', '真实性交叉验证', '关联风险信号'],
  },
  {
    key: 'due_diligence',
    label: '综合尽调',
    title: '综合尽调报告',
    subtitle: '综合评分 · 经营真实性 · 舞弊 · 同业对标',
    tier: 'general',
    description: '一站式覆盖评分、真实性、舞弊与同业对标。',
    dataFocus: ['财务数据', '税务数据', '发票数据', '企业基础信息'],
    motif: 'compass',
    accent: '#003366',
    chapters: ['综合评分切片', '经营真实性', '发票舞弊检测', '行业对标', '预警清单'],
  },
  {
    key: 'profile',
    label: '企业画像',
    title: '企业画像报告',
    subtitle: '规模 · 地区 · 行业 · 信用等级',
    tier: 'general',
    description: '刻画样本的规模、地区、行业与信用等级结构。',
    dataFocus: ['企业基础信息'],
    motif: 'badge',
    accent: '#6d28d9',
    chapters: ['地区信用画像', '行业规模画像', '行业基准定位', '信用等级分布'],
  },
  {
    key: 'overview',
    label: '综合总览',
    title: '综合总览报告',
    subtitle: '六维画像 · 信号总览 · 五场景摘要索引',
    tier: 'general',
    description: '汇总全样本六维画像与风险信号总览，并为五套专项切片提供摘要索引。',
    dataFocus: ['财务数据', '税务数据', '发票数据', '企业基础信息'],
    motif: 'compass',
    accent: '#003366',
    chapters: ['六维综合画像', '风险信号总览', '财务健康摘要', '税务合规摘要', '发票舞弊摘要', '经营真实性摘要'],
  },
];
