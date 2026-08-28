import type { DimensionType, FunctionType } from '@/types/chat';

/** 维度 → 中文前缀 */
const DIMENSION_PREFIX: Record<DimensionType, string> = {
  overall: '分析整体',
  industry: '分析各行业的',
  region: '分析各地区的',
  time: '分析各时间段的',
  signal: '分析各信号的',
};

/** 功能 → 中文后缀 */
const FUNCTION_SUFFIX: Record<FunctionType, string> = {
  score: '风险评分情况',
  authenticity: '经营真实性',
  fraud: '反欺诈分析',
  benchmark: '行业基准对比',
  trend: '趋势走向',
};

/** 根据维度和功能拼接查询文本 */
export function buildQueryText(
  dimension: DimensionType | null,
  func: FunctionType | null
): string {
  const prefix = dimension ? DIMENSION_PREFIX[dimension] : '';
  const suffix = func ? FUNCTION_SUFFIX[func] : '';
  return `${prefix}${suffix}`;
}

/** 简单意图解析（前端预判） */
export function parseIntent(text: string): {
  dimension: DimensionType | null;
  func: FunctionType | null;
} {
  let dimension: DimensionType | null = null;
  let func: FunctionType | null = null;

  if (/整体|全部|所有/.test(text)) dimension = 'overall';
  else if (/行业|产业/.test(text)) dimension = 'industry';
  else if (/地区|区域|省|市/.test(text)) dimension = 'region';
  else if (/时间|月|季度|年|趋势/.test(text)) dimension = 'time';
  else if (/信号|预警|异常/.test(text)) dimension = 'signal';

  if (/评分|打分|分数/.test(text)) func = 'score';
  else if (/真实|造假|偏差/.test(text)) func = 'authenticity';
  else if (/欺诈|虚开|错配/.test(text)) func = 'fraud';
  else if (/基准|对比|比较/.test(text)) func = 'benchmark';
  else if (/趋势|走向|变化/.test(text)) func = 'trend';

  return { dimension, func };
}
