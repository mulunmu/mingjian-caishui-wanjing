/** 报告场景/模块（与后端 report_templates.SCENARIOS 对齐） */
export interface ReportScenarioDef {
  key: string;
  label: string;
  tier: 'general' | 'premium';
  description: string;
  chapters: string[];
}

export const REPORT_SCENARIOS: ReportScenarioDef[] = [
  {
    key: 'general',
    label: '行业趋势风控',
    tier: 'general',
    description: '样本覆盖、行业走向与主要风险信号。',
    chapters: ['行业趋势', '信用与纳税健康', '风险信号总览', '经营真实性'],
  },
  {
    key: 'fraud',
    label: '欺诈舞弊风控',
    tier: 'general',
    description: '进销错配、红冲、集中度与异常检测。',
    chapters: ['发票舞弊切片', '真实性交叉验证', '关联风险信号'],
  },
  {
    key: 'due_diligence',
    label: '尽调组合',
    tier: 'general',
    description: '评分、真实性、舞弊与同业对标一站式。',
    chapters: ['综合评分切片', '真实性', '舞弊检测', '行业对标', '预警清单'],
  },
  {
    key: 'fundamental',
    label: '基本面趋势',
    tier: 'general',
    description: '同比趋势与行业基准，少涉舞弊细节。',
    chapters: ['趋势走向', '行业基准', '地区评分'],
  },
  {
    key: 'custom',
    label: '定制深度风控',
    tier: 'premium',
    description: '全维度切片组合（付费），开发期隔离。',
    chapters: ['地区评分', '行业趋势', '真实性', '舞弊', '对标', '预警'],
  },
];
