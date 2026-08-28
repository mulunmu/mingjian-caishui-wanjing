import Card from '@/components/ui/Card';
import PieChart from '@/components/charts/PieChart';

interface RiskDistributionProps {
  data: { name: string; value: number }[];
  total: number;
}

export default function RiskDistribution({ data, total }: RiskDistributionProps) {
  return (
    <Card index={0} className="p-5">
      <h3 className="text-sm font-semibold text-warm-700 mb-3">风险分布</h3>
      <div className="relative">
        <PieChart data={data} innerRadius="60%" height={220} />
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ top: -10 }}>
          <div className="text-center">
            <div className="text-2xl font-bold text-warm-800 font-number">{total}</div>
            <div className="text-xs text-warm-400">企业总数</div>
          </div>
        </div>
      </div>
    </Card>
  );
}
