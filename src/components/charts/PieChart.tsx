import ReactECharts from 'echarts-for-react';
import { warmTheme } from './chartTheme';

interface PieChartProps {
  data: {
    name: string;
    value: number;
  }[];
  title?: string;
  height?: number;
  innerRadius?: string;
  /** 饼图垂直位置（默认无标题时 '45%'） */
  centerY?: string;
}

export default function PieChart({
  data,
  title,
  height = 260,
  innerRadius = '55%',
  centerY,
}: PieChartProps) {
  const option = {
    ...warmTheme,
    title: title
      ? {
          text: title,
          left: 'center',
          top: 0,
          ...warmTheme.title,
        }
      : undefined,
    tooltip: {
      ...warmTheme.tooltip,
      trigger: 'item' as const,
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      ...warmTheme.legend,
      bottom: 0,
      data: data.map((d) => d.name),
    },
    series: [
      {
        type: 'pie',
        radius: [innerRadius, '75%'],
        center: ['50%', centerY || (title ? '55%' : '45%')],
        data,
        label: { show: false },
        emphasis: {
          label: { show: true, fontWeight: 'bold' },
          itemStyle: { shadowBlur: 10, shadowColor: 'rgba(44, 36, 24, 0.15)' },
        },
        itemStyle: {
          borderColor: '#fff',
          borderWidth: 2,
        },
        animationType: 'scale' as const,
        animationDuration: 800,
      },
    ],
    color: warmTheme.color,
  };

  return <ReactECharts option={option} style={{ height }} opts={{ renderer: 'svg' }} />;
}
