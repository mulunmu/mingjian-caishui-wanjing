import ReactECharts from 'echarts-for-react';
import { warmTheme } from './chartTheme';

interface LineChartProps {
  data: {
    categories: string[];
    series: { name: string; values: number[] }[];
    title?: string;
  };
  height?: number;
}

export default function LineChart({ data, height = 260 }: LineChartProps) {
  const option = {
    ...warmTheme,
    title: data.title ? { text: data.title, ...warmTheme.title } : undefined,
    tooltip: { ...warmTheme.tooltip, trigger: 'axis' as const },
    legend: {
      ...warmTheme.legend,
      top: data.title ? 30 : 0,
      data: data.series.map((s) => s.name),
    },
    grid: {
      left: 40,
      right: 20,
      top: data.title ? 60 : 30,
      bottom: 30,
    },
    xAxis: {
      type: 'category' as const,
      data: data.categories,
      ...warmTheme.categoryAxis,
    },
    yAxis: { type: 'value' as const, ...warmTheme.valueAxis },
    series: data.series.map((s, i) => ({
      name: s.name,
      type: 'line',
      data: s.values,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2 },
      itemStyle: { color: warmTheme.color[i] },
      areaStyle: {
        color: {
          type: 'linear' as const,
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: warmTheme.color[i] + '20' },
            { offset: 1, color: warmTheme.color[i] + '02' },
          ],
        },
      },
      animationDuration: 800,
    })),
  };

  return <ReactECharts option={option} style={{ height }} opts={{ renderer: 'svg' }} />;
}
