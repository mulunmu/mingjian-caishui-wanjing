import ReactECharts from 'echarts-for-react';
import { warmTheme } from './chartTheme';

interface HeatmapProps {
  data: {
    xLabels: string[];
    yLabels: string[];
    values: [number, number, number][]; // [x, y, value]
    title?: string;
  };
  height?: number;
}

export default function Heatmap({ data, height = 280 }: HeatmapProps) {
  const maxVal = Math.max(...data.values.map((v) => v[2]), 1);

  const option = {
    ...warmTheme,
    title: data.title ? { text: data.title, ...warmTheme.title } : undefined,
    tooltip: {
      ...warmTheme.tooltip,
      formatter: (params: { value: [number, number, number] }) => {
        const [x, y, val] = params.value;
        return `${data.xLabels[x]} × ${data.yLabels[y]}: ${val}`;
      },
    },
    grid: { left: 80, right: 20, top: data.title ? 40 : 20, bottom: 40 },
    xAxis: {
      type: 'category' as const,
      data: data.xLabels,
      ...warmTheme.categoryAxis,
    },
    yAxis: {
      type: 'category' as const,
      data: data.yLabels,
      ...warmTheme.categoryAxis,
    },
    visualMap: {
      min: 0,
      max: maxVal,
      calculable: true,
      orient: 'horizontal' as const,
      left: 'center',
      bottom: 0,
      // 单色序（米金 → 深金）：仅明度变化，红/绿/蓝盲均可区分。
      inRange: {
        color: ['#F7F4EE', '#A18A5F'],
      },
      textStyle: { color: '#7A6E5E' },
    },
    series: [
      {
        type: 'heatmap',
        data: data.values,
        label: {
          show: true,
          fontSize: 10,
          // 深色格白字、浅色格深字，保证数值对比度。
          color: (params: { value?: [number, number, number] }) => {
            const val = params.value?.[2] ?? 0;
            return val >= maxVal * 0.6 ? '#FFFFFF' : '#2C2418';
          },
        },
        emphasis: {
          itemStyle: { shadowBlur: 6, shadowColor: 'rgba(44, 36, 24, 0.2)' },
        },
        animationDuration: 800,
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} opts={{ renderer: 'svg' }} />;
}
