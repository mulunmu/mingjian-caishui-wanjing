import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Search, Filter, RefreshCw } from 'lucide-react';
import { riskApi } from '@/api/risk';
import type { FraudAnalysisItem } from '@/types/risk';
import Card from '@/components/ui/Card';
import Skeleton from '@/components/ui/Skeleton';

const riskLevelColors: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: 'bg-terracotta/10', text: 'text-terracotta', label: '高风险' },
  medium: { bg: 'bg-amber/10', text: 'text-amber', label: '中风险' },
  low: { bg: 'bg-sage/10', text: 'text-sage', label: '低风险' },
};

export default function FraudPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<FraudAnalysisItem[]>([]);
  const [meta, setMeta] = useState({ sample_count: 0, flagged_count: 0, avg_composite: null as number | null });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [industry, setIndustry] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const batch = await riskApi.getFraud(industry || undefined);
      setData(batch.rows);
      setMeta({
        sample_count: batch.sample_count,
        flagged_count: batch.flagged_count,
        avg_composite: batch.avg_composite,
      });
    } catch (e) {
      setData([]);
      setMeta({ sample_count: 0, flagged_count: 0, avg_composite: null });
      setError(e instanceof Error ? e.message : '反欺诈数据暂不可用，请稍后重试。');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [industry]);

  const filteredData = data.filter((item) => {
    if (!searchTerm) return true;
    return (
      (item.display_name || '').includes(searchTerm) ||
      (item.display_label || '').includes(searchTerm) ||
      (item.industry_l1 || '').includes(searchTerm)
    );
  });

  const industries = ['', '批发零售', '制造', '建筑', 'IT软件', '服务'];

  return (
    <div className="h-full flex flex-col bg-warm-50">
      <div className="bg-white border-b border-warm-200 px-6 py-4">
        <h1 className="text-xl font-semibold text-warm-800">反欺诈分析</h1>
        <p className="text-sm text-warm-500 mt-1">进销商品错配检测 · 红字发票分析 · 集中度分析</p>
      </div>

      <div className="bg-white border-b border-warm-200 px-6 py-3 flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-warm-400" />
          <input
            type="text"
            placeholder="搜索企业..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full h-9 pl-10 pr-4 rounded-lg border border-warm-200 bg-warm-50 text-sm text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
          />
        </div>

        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-warm-400" />
          <select
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="h-9 px-3 rounded-lg border border-warm-200 bg-white text-sm text-warm-700 focus:outline-none focus:border-amber"
          >
            <option value="">全部行业</option>
            {industries.filter(Boolean).map((ind) => (
              <option key={ind} value={ind}>{ind}</option>
            ))}
          </select>
        </div>

        <button
          onClick={() => void fetchData()}
          disabled={isLoading}
          className="flex items-center gap-2 h-9 px-3 rounded-lg border border-warm-200 text-sm text-warm-600 hover:bg-warm-100 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {isLoading ? (
          <div className="max-w-5xl mx-auto space-y-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} height="80px" />
            ))}
          </div>
        ) : error ? (
          <div className="max-w-5xl mx-auto flex flex-col items-center justify-center py-20">
            <AlertTriangle className="w-12 h-12 text-terracotta mb-4" />
            <p className="text-warm-700 font-medium">加载失败</p>
            <p className="text-sm text-warm-500 mt-2 text-center max-w-md">{error}</p>
            <button
              type="button"
              onClick={() => void fetchData()}
              className="mt-4 h-9 px-4 rounded-lg bg-amber text-white text-sm hover:opacity-90"
            >
              重试
            </button>
          </div>
        ) : (
          <div className="max-w-5xl mx-auto space-y-4">
            <div className="grid grid-cols-3 gap-4 mb-6">
              <Card index={0} className="p-4">
                <div className="text-sm text-warm-500 mb-1">批次样本数</div>
                <div className="text-2xl font-bold text-warm-800">{meta.sample_count}</div>
              </Card>
              <Card index={1} className="p-4">
                <div className="text-sm text-warm-500 mb-1">标记样本数</div>
                <div className="text-2xl font-bold text-terracotta">{meta.flagged_count}</div>
              </Card>
              <Card index={2} className="p-4">
                <div className="text-sm text-warm-500 mb-1">批次均分</div>
                <div className="text-2xl font-bold text-warm-800">
                  {meta.avg_composite != null ? meta.avg_composite.toFixed(1) : '—'}
                </div>
              </Card>
            </div>

            <div className="bg-white rounded-xl border border-warm-200 overflow-hidden">
              <div className="grid grid-cols-7 gap-2 px-5 py-3 bg-warm-100/50 text-xs font-medium text-warm-600">
                <div>企业标识</div>
                <div>行业</div>
                <div>综合风险分</div>
                <div>风险等级</div>
                <div>进销错配分</div>
                <div>红字发票分</div>
                <div>集中度分</div>
              </div>
              {filteredData.map((item, i) => {
                const riskStyle = riskLevelColors[item.fraud_risk_level || 'medium'] || riskLevelColors.medium;
                const canNavigate = Boolean(item.enterprise_id && !String(item.enterprise_id).startsWith('flag-'));
                return (
                  <div
                    key={item.enterprise_id || i}
                    className={`grid grid-cols-7 gap-2 px-5 py-3 border-t border-warm-100 transition-colors ${canNavigate ? 'hover:bg-warm-50 cursor-pointer' : ''}`}
                    onClick={() => canNavigate && navigate(`/enterprise/${item.enterprise_id}`)}
                  >
                    <div className="text-sm text-warm-800 font-medium">{item.display_name || item.display_label || item.enterprise_id}</div>
                    <div className="text-sm text-warm-600">{item.industry_l1 || '-'}</div>
                    <div className="text-sm text-warm-800 font-mono">{item.fraud_composite_score?.toFixed(1) ?? '-'}</div>
                    <div>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${riskStyle.bg} ${riskStyle.text}`}>
                        {riskStyle.label}
                      </span>
                    </div>
                    <div className="text-sm text-warm-600 font-mono">{item.scbm_mismatch_score?.toFixed(1) ?? '-'}</div>
                    <div className="text-sm text-warm-600 font-mono">{item.red_invoice_score?.toFixed(1) ?? '-'}</div>
                    <div className="text-sm text-warm-600 font-mono">{item.concentration_score?.toFixed(1) ?? '-'}</div>
                  </div>
                );
              })}
            </div>

            {filteredData.length === 0 && (
              <div className="flex flex-col items-center justify-center py-20">
                <AlertTriangle className="w-12 h-12 text-warm-300 mb-4" />
                <p className="text-warm-500">暂无匹配数据（非演示伪造）</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
