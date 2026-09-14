/** ECharts 主题：藏青 / 古铜金 / 语义色（与品牌令牌对齐） */
export const warmTheme = {
  color: ['#152446', '#A18A5F', '#059669', '#F57C00', '#3B5B7A', '#8F7850'],
  backgroundColor: 'transparent',
  textStyle: {
    color: '#4A5568',
    fontFamily: 'Inter, PingFang SC, sans-serif',
  },
  title: {
    textStyle: { color: '#0B1C3E' },
    subtextStyle: { color: '#4A5568' },
  },
  line: {
    itemStyle: { borderWidth: 2 },
    lineStyle: { width: 2 },
    symbolSize: 6,
    symbol: 'circle',
    smooth: true,
  },
  bar: {
    itemStyle: {
      barBorderWidth: 0,
      barBorderColor: '#ccc',
    },
  },
  pie: {
    itemStyle: {
      borderWidth: 2,
      borderColor: '#ffffff',
    },
  },
  categoryAxis: {
    axisLine: { show: true, lineStyle: { color: '#E4DED3' } },
    axisTick: { show: false },
    axisLabel: { color: '#4A5568', fontSize: 11 },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#4A5568', fontSize: 11 },
    splitLine: { lineStyle: { color: '#E4DED3', type: 'dashed' as const } },
  },
  tooltip: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E4DED3',
    borderWidth: 1,
    textStyle: { color: '#0B1C3E', fontSize: 12 },
    extraCssText: 'box-shadow: 0 4px 16px rgba(11, 28, 62, 0.08);',
  },
  legend: {
    textStyle: { color: '#4A5568', fontSize: 12 },
  },
};
