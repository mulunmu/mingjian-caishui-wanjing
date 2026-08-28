import ReactECharts from 'echarts-for-react';
import { warmTheme } from './chartTheme';

interface ScatterChartProps {
  data: {
    x: number[];
    y: number[];
    x_label?: string;
    y_label?: string;
  };
  height?: number;
}

/** 两指标相关性散点图（后端 correlation_scatter_chart 已对齐 x/y）。 */
export default function ScatterChart({ data, height = 280 }: ScatterChartProps) {
  const points = (data.x ?? []).map(
    (x, i) => [x, data.y?.[i] ?? 0] as [number, number]
  );

  const option = {
    ...warmTheme,
    grid: { left: 60, right: 28, top: 24, bottom: 48 },
    tooltip: {
      ...warmTheme.tooltip,
      formatter: (params: { value: [number, number] }) => {
        const [x, y] = params.value;
        return `${data.x_label ?? 'x'}: ${x}<br/>${data.y_label ?? 'y'}: ${y}`;
      },
    },
    xAxis: {
      type: 'value' as const,
      name: data.x_label,
      ...warmTheme.valueAxis,
    },
    yAxis: {
      type: 'value' as const,
      name: data.y_label,
      ...warmTheme.valueAxis,
    },
    series: [
      {
        type: 'scatter' as const,
        data: points,
        symbolSize: 10,
        itemStyle: { color: '#C08B30' },
        emphasis: {
          itemStyle: { shadowBlur: 8, shadowColor: 'rgba(44, 36, 24, 0.2)' },
        },
        animationDuration: 800,
      },
    ],
  };

  return <ReactECharts option={option} style={{ height }} opts={{ renderer: 'svg' }} />;
}
