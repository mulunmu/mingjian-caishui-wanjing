import ReactECharts from 'echarts-for-react';
import { warmTheme } from './chartTheme';

interface RadarChartProps {
  data: {
    indicators: { name: string; max: number }[];
    values: number[];
    title?: string;
  };
  height?: number;
}

export default function RadarChart({ data, height = 280 }: RadarChartProps) {
  const option = {
    ...warmTheme,
    title: data.title ? { text: data.title, ...warmTheme.title } : undefined,
    tooltip: { ...warmTheme.tooltip },
    radar: {
      indicator: data.indicators,
      shape: 'polygon' as const,
      axisName: { color: '#7A6E5E', fontSize: 11 },
      splitArea: {
        areaStyle: {
          color: ['#F7F4EE', '#EFEBE3', '#F7F4EE', '#EFEBE3'],
        },
      },
      splitLine: { lineStyle: { color: '#EDE5DA' } },
      axisLine: { lineStyle: { color: '#EDE5DA' } },
    },
    series: [
      {
        type: 'radar',
        data: [{ value: data.values }],
        areaStyle: {
          color: 'rgba(161, 138, 95, 0.15)',
        },
        lineStyle: { color: '#A18A5F', width: 2 },
        itemStyle: { color: '#A18A5F' },
        animationDuration: 800,
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} opts={{ renderer: 'svg' }} />;
}
