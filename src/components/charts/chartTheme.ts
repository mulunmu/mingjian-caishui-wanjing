/** ECharts 暖色主题 */
export const warmTheme = {
  color: ['#C08B30', '#D4763A', '#5A9E6F', '#6A8FA8', '#B8977E', '#8B7355'],
  backgroundColor: 'transparent',
  textStyle: {
    color: '#7A6E5E',
    fontFamily: 'Inter, PingFang SC, sans-serif',
  },
  title: {
    textStyle: { color: '#2C2418' },
    subtextStyle: { color: '#7A6E5E' },
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
    axisLine: { show: true, lineStyle: { color: '#EDE5DA' } },
    axisTick: { show: false },
    axisLabel: { color: '#7A6E5E', fontSize: 11 },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#7A6E5E', fontSize: 11 },
    splitLine: { lineStyle: { color: '#EDE5DA', type: 'dashed' as const } },
  },
  tooltip: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E8DFD3',
    borderWidth: 1,
    textStyle: { color: '#2C2418', fontSize: 12 },
    extraCssText: 'box-shadow: 0 4px 16px rgba(44, 36, 24, 0.08);',
  },
  legend: {
    textStyle: { color: '#7A6E5E', fontSize: 12 },
  },
};
