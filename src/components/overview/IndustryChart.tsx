import Card from '@/components/ui/Card';
import BarChart from '@/components/charts/BarChart';

interface IndustryChartProps {
  data: { name: string; value: number }[];
}

export default function IndustryChart({ data }: IndustryChartProps) {
  return (
    <Card index={1} className="p-5">
      <h3 className="text-sm font-semibold text-warm-700 mb-3">行业分布</h3>
      <BarChart
        data={{
          categories: data.map((d) => d.name),
          values: data.map((d) => d.value),
        }}
        horizontal
        height={220}
      />
    </Card>
  );
}
