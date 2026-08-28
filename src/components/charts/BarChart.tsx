import ReactECharts from 'echarts-for-react';
import { warmTheme } from './chartTheme';

interface BarChartProps {
  data: {
    categories: string[];
    values?: number[];
    series?: { name: string; values: number[] }[];
    title?: string;
  };
  horizontal?: boolean;
  height?: number;
}

export default function BarChart({ data, horizontal = false, height = 260 }: BarChartProps) {
  // 兼容单系列扁平 {values} 与多系列 {series}（对话适配层统一转成其中一种）
  const series = data.series?.length
    ? data.series
    : [{ name: data.title ?? '', values: data.values ?? [] }];
  const showLegend = series.length > 1;

  const option = {
    ...warmTheme,
    title: data.title ? { text: data.title, ...warmTheme.title } : undefined,
    tooltip: { ...warmTheme.tooltip, trigger: 'axis' as const },
    legend: showLegend ? { ...warmTheme.legend, top: data.title ? 30 : 0 } : undefined,
    grid: {
      left: horizontal ? 80 : 40,
      right: 20,
      top: data.title ? (showLegend ? 60 : 40) : showLegend ? 30 : 20,
      bottom: 30,
    },
    xAxis: horizontal
      ? { type: 'value' as const, ...warmTheme.valueAxis }
      : { type: 'category' as const, data: data.categories, ...warmTheme.categoryAxis },
    yAxis: horizontal
      ? { type: 'category' as const, data: data.categories, ...warmTheme.categoryAxis }
      : { type: 'value' as const, ...warmTheme.valueAxis },
    series: series.map((s, i) => ({
      name: s.name,
      type: 'bar',
      data: s.values,
      barWidth: horizontal ? 16 : 24,
      itemStyle: {
        borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
        color: showLegend
          ? warmTheme.color[i % warmTheme.color.length]
          : {
              type: 'linear' as const,
              x: horizontal ? 0 : 0,
              y: horizontal ? 0 : 1,
              x2: horizontal ? 1 : 0,
              y2: 0,
              colorStops: [
                { offset: 0, color: '#C08B30' },
                { offset: 1, color: '#D4763A' },
              ],
            },
      },
      animationDuration: 800,
      animationEasing: 'cubicOut' as const,
    })),
  };

  return <ReactECharts option={option} style={{ height }} opts={{ renderer: 'svg' }} />;
}
