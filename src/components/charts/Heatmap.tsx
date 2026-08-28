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
  const maxVal = Math.max(...data.values.map((v) => v[2]));

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
      inRange: {
        color: ['#FAF6F1', '#C08B30'],
      },
      textStyle: { color: '#7A6E5E' },
    },
    series: [
      {
        type: 'heatmap',
        data: data.values,
        label: { show: true, color: '#2C2418', fontSize: 10 },
        emphasis: {
          itemStyle: { shadowBlur: 6, shadowColor: 'rgba(44, 36, 24, 0.2)' },
        },
        animationDuration: 800,
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} opts={{ renderer: 'svg' }} />;
}
