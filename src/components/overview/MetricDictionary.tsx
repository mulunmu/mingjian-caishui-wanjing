import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronRight, BookOpen, Search } from 'lucide-react';
import { metricsApi } from '@/api/risk';
import type { MetricDefinition } from '@/types/risk';
import Card from '@/components/ui/Card';
import Skeleton from '@/components/ui/Skeleton';
import Badge from '@/components/ui/Badge';
import Divider from '@/components/ui/Divider';

// 演示数据
const demoMetrics: MetricDefinition[] = [
  {
    metric_key: 'score_overall',
    name: '综合评分',
    description: '基于六维指标体系的加权综合评分，反映企业整体税务健康状况',
    metric_type: 'score',
    formula: '税务健康×0.20 + 经营真实性×0.20 + 发票健康×0.15 + 行业地位×0.15 + 法律合规×0.15 + 财务健康×0.15',
    unit: '分',
    grain: '企业级',
    source_fields: ['tax_health', 'authenticity', 'invoice', 'industry', 'legal', 'finance'],
    dimensions: ['行业', '地区', '时间'],
  },
  {
    metric_key: 'score_tax_health',
    name: '税务健康评分',
    description: '衡量企业税务申报合规性、缴税及时性和税负率合理性',
    metric_type: 'score',
    formula: '按时缴税率×0.4 + 税负率偏离度×0.3 + 申报完整性×0.3',
    unit: '分',
    grain: '企业级',
    source_fields: ['tax_on_time_rate', 'tax_burden_rate', 'filing_completeness'],
    dimensions: ['行业', '地区'],
  },
  {
    metric_key: 'score_authenticity',
    name: '经营真实性评分',
    description: '通过交叉验证企业进销数据、发票信息、社保数据等判断经营真实性',
    metric_type: 'score',
    formula: '进销匹配度×0.35 + 发票一致性×0.35 + 社保交叉验证×0.30',
    unit: '分',
    grain: '企业级',
    source_fields: ['purchase_sales_match', 'invoice_consistency', 'social_security_cross'],
    dimensions: ['行业'],
  },
  {
    metric_key: 'scbm_mismatch_score',
    name: '进销错配分',
    description: '检测企业进项与销项商品类别是否存在异常错配',
    metric_type: 'risk_signal',
    formula: 'Σ(进销HS编码差异权重) / 总交易笔数',
    unit: '分',
    grain: '企业级',
    source_fields: ['purchase_codes', 'sales_codes'],
    dimensions: ['行业', '商品类别'],
  },
  {
    metric_key: 'red_invoice_score',
    name: '红字发票风险分',
    description: '分析红字发票占比、频率和金额异常',
    metric_type: 'risk_signal',
    formula: '红字发票金额占比×0.5 + 红字发票频率异常度×0.5',
    unit: '分',
    grain: '企业级',
    source_fields: ['red_invoice_amount', 'total_invoice_amount', 'red_invoice_count'],
    dimensions: ['行业'],
  },
  {
    metric_key: 'debt_ratio',
    name: '资产负债率',
    description: '企业总负债与总资产的比率，反映财务杠杆水平',
    metric_type: 'financial',
    formula: '总负债 / 总资产 × 100%',
    unit: '%',
    grain: '企业级',
    source_fields: ['total_liabilities', 'total_assets'],
    dimensions: ['行业', '规模'],
  },
];

const typeLabels: Record<string, { label: string; level: 'high' | 'medium' | 'low' | 'info' }> = {
  // 演示/旧标签
  score: { label: '评分指标', level: 'info' },
  risk_signal: { label: '风险信号', level: 'high' },
  financial: { label: '财务指标', level: 'medium' },
  operational: { label: '经营指标', level: 'low' },
  // 真实字典口径（后端 metric_type）
  derived: { label: '衍生指标', level: 'info' },
  computed: { label: '计算指标', level: 'info' },
  ratio: { label: '比率指标', level: 'medium' },
  simple: { label: '基础指标', level: 'low' },
};

const grainLabels: Record<string, string> = {
  enterprise: '企业级',
  industry: '行业级',
  region: '地区级',
  time: '时间级',
};

export default function MetricDictionary() {
  const [metrics, setMetrics] = useState<MetricDefinition[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDemo, setIsDemo] = useState(false);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchMetrics = async () => {
      setIsLoading(true);
      try {
        const res = await metricsApi.getDictionary();
        // 后端返回对象 { metrics, source_fields, dimensions }，取 metrics 数组；
        // 兼容旧扁平数组返回。取不到真实口径才回退演示数据。
        const list = Array.isArray(res) ? res : (res?.metrics ?? []);
        if (list.length > 0) {
          setMetrics(list);
          setIsDemo(false);
        } else {
          setMetrics(demoMetrics);
          setIsDemo(true);
        }
      } catch {
        setMetrics(demoMetrics);
        setIsDemo(true);
      } finally {
        setIsLoading(false);
      }
    };
    fetchMetrics();
  }, []);

  const filteredMetrics = metrics.filter((m) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      m.name.toLowerCase().includes(term) ||
      m.metric_key.toLowerCase().includes(term) ||
      (m.description || '').toLowerCase().includes(term)
    );
  });

  const toggleExpand = (key: string) => {
    setExpandedKey(expandedKey === key ? null : key);
  };

  if (isLoading) {
    return (
      <Card index={4} className="p-5">
        <h3 className="text-sm font-semibold text-warm-700 mb-3">指标字典</h3>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} height="48px" />
          ))}
        </div>
      </Card>
    );
  }

  return (
    <Card index={4} className="p-5">
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-amber" />
          <h3 className="text-sm font-semibold text-warm-700">指标字典</h3>
          <span className="text-xs text-warm-400">共 {metrics.length} 项指标</span>
          {isDemo && (
            <span className="text-[10px] text-amber bg-amber/10 px-1.5 py-0.5 rounded">
              演示示例（字典服务未接入）
            </span>
          )}
        </div>
      </div>

      {/* 搜索栏 */}
      <div className="relative mb-3">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-warm-400" />
        <input
          type="text"
          placeholder="搜索指标名称或编码..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full h-8 pl-8 pr-3 rounded-lg border border-warm-200 bg-warm-50 text-xs text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
        />
      </div>

      {/* 指标列表 */}
      <div className="space-y-1.5 max-h-[400px] overflow-y-auto pr-1">
        {filteredMetrics.map((metric, i) => {
          const isExpanded = expandedKey === metric.metric_key;
          const typeInfo = typeLabels[metric.metric_type || ''] || { label: metric.metric_type || '其他', level: 'info' as const };

          return (
            <motion.div
              key={metric.metric_key}
              variants={{
                hidden: { opacity: 0, y: 4 },
                visible: (idx: number) => ({
                  opacity: 1,
                  y: 0,
                  transition: { delay: idx * 0.04, duration: 0.2 },
                }),
              }}
              initial="hidden"
              animate="visible"
              custom={i}
              className="border border-warm-100 rounded-lg overflow-hidden hover:border-warm-200 transition-colors"
            >
              {/* 指标标题行 */}
              <button
                onClick={() => toggleExpand(metric.metric_key)}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-warm-50 transition-colors"
              >
                {isExpanded ? (
                  <ChevronDown className="w-3.5 h-3.5 text-warm-400 flex-shrink-0" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-warm-400 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-warm-800 truncate">{metric.name}</span>
                    <Badge level={typeInfo.level}>{typeInfo.label}</Badge>
                    {metric.unit && (
                      <span className="text-[10px] text-warm-400 bg-warm-100 px-1.5 py-0.5 rounded">
                        {metric.unit}
                      </span>
                    )}
                  </div>
                  <span className="text-[11px] text-warm-400 font-mono">{metric.metric_key}</span>
                </div>
              </button>

              {/* 展开详情 */}
              <AnimatePresence>
                {isExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <Divider />
                    <div className="px-3 py-3 space-y-2.5 bg-warm-50/50">
                      {/* 口径说明 */}
                      {metric.description && (
                        <div>
                          <span className="text-[10px] font-medium text-warm-500 uppercase tracking-wider">口径说明</span>
                          <p className="text-xs text-warm-700 mt-0.5 leading-relaxed">{metric.description}</p>
                        </div>
                      )}

                      {/* 计算公式 */}
                      {metric.formula && (
                        <div>
                          <span className="text-[10px] font-medium text-warm-500 uppercase tracking-wider">计算公式</span>
                          <p className="text-xs text-warm-700 mt-0.5 font-mono bg-white px-2 py-1.5 rounded border border-warm-100">
                            {metric.formula}
                          </p>
                        </div>
                      )}

                      {/* 元信息行 */}
                      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                        {metric.grain && (
                          <div>
                            <span className="text-[10px] text-warm-400">粒度</span>
                            <span className="text-xs text-warm-700 ml-1">{grainLabels[metric.grain] ?? metric.grain}</span>
                          </div>
                        )}
                        {metric.source_fields && metric.source_fields.length > 0 && (
                          <div>
                            <span className="text-[10px] text-warm-400">数据源</span>
                            <span className="text-xs text-warm-700 ml-1">{metric.source_fields.join(', ')}</span>
                          </div>
                        )}
                        {metric.dimensions && metric.dimensions.length > 0 && (
                          <div>
                            <span className="text-[10px] text-warm-400">维度</span>
                            <div className="inline-flex gap-1 ml-1">
                              {metric.dimensions.map((dim) => (
                                <span key={dim} className="text-[10px] text-amber bg-amber/10 px-1.5 py-0.5 rounded">
                                  {dim}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>

      {/* 空状态 */}
      {filteredMetrics.length === 0 && (
        <div className="flex flex-col items-center justify-center py-8">
          <Search className="w-8 h-8 text-warm-300 mb-2" />
          <p className="text-xs text-warm-400">无匹配指标</p>
        </div>
      )}
    </Card>
  );
}
