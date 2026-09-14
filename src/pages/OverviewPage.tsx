import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Building2,
  ShieldAlert,
  Bell,
  BarChart3,
  ChevronRight,
  ChevronDown,
  Loader2,
} from 'lucide-react';
import useOverviewStore from '@/stores/overviewStore';
import MetricDictionary from '@/components/overview/MetricDictionary';
import Badge from '@/components/ui/Badge';
import Skeleton from '@/components/ui/Skeleton';
import PieChart from '@/components/charts/PieChart';
import BarChart from '@/components/charts/BarChart';
import type { WarningEnterprise, IndustryProfileItem } from '@/types/overview';

const TOP_N = 10;

/* ── 入场 ── */
const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.28, ease: [0.4, 0, 0.2, 1] },
  }),
};

/* ── 行业画像对标：0-1 → %，剔除弃权（null/0）行业 ── */
function industryBarData(profiles: IndustryProfileItem[], field: keyof IndustryProfileItem) {
  const rows = profiles
    .filter((p) => typeof p[field] === 'number' && (p[field] as number) > 0)
    .map((p) => ({ name: p.industry_l1, value: (p[field] as number) * 100 }))
    .sort((a, b) => b.value - a.value);
  return {
    categories: rows.map((r) => r.name),
    values: rows.map((r) => r.value),
  };
}

function KpiCard({
  icon: Icon,
  label,
  value,
  color,
  index,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: any;
  label: string;
  value: string | number;
  color: string;
  index: number;
}) {
  return (
    <motion.div custom={index} variants={fadeUp} initial="hidden" animate="visible">
      <div className="bg-white rounded-xl border border-warm-200 px-5 py-4 flex items-center gap-3 shadow-sm">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={18} className="text-white" />
        </div>
        <div>
          <p className="text-[11px] text-warm-400 leading-none">{label}</p>
          <p className="text-xl font-bold text-warm-800 leading-tight mt-1">{value}</p>
        </div>
      </div>
    </motion.div>
  );
}

function AlertRow({ ent, onClick }: { ent: WarningEnterprise; onClick: () => void }) {
  const score = ent.overall_score ?? 0;
  return (
    <tr
      onClick={onClick}
      className="border-b border-warm-100 last:border-0 hover:bg-red-50/30 cursor-pointer transition-colors"
    >
      <td className="py-3 pl-4 pr-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
          <span className="text-[13px] text-warm-700 font-medium truncate max-w-[180px]">
            {ent.display_name || ent.enterprise_name || ent.display_label}
          </span>
        </div>
      </td>
      <td className="py-3 px-2 text-[13px] text-warm-500">{ent.industry_l1 || '-'}</td>
      <td className="py-3 px-2 text-right">
        <span
          className={`text-[13px] font-semibold tabular-nums ${
            score < 0 ? 'text-red-600' : 'text-warm-700'
          }`}
        >
          {score.toFixed(1)}
        </span>
      </td>
      <td className="py-3 px-2 text-center">
        <Badge level="high">高风险</Badge>
      </td>
      <td className="py-3 pr-4 pl-2 w-6 text-right">
        <ChevronRight size={13} className="text-warm-300 inline" />
      </td>
    </tr>
  );
}

export default function OverviewPage() {
  const navigate = useNavigate();
  const {
    kpi,
    riskDistribution,
    industryProfiles,
    warnings,
    topWarningsTotal,
    showAllAlerts,
    isLoading,
    isExpanding,
    error,
    fetchOverview,
    expandAllAlerts,
    collapseAlerts,
  } = useOverviewStore();
  const [showDict, setShowDict] = useState(false);
  const [showBench, setShowBench] = useState(false);

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="max-w-[1100px] mx-auto space-y-5">
          <Skeleton height="32px" width="180px" />
          <Skeleton height="72px" className="rounded-xl" />
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} height="72px" className="rounded-xl" />
            ))}
          </div>
          <div className="grid grid-cols-5 gap-5">
            <div className="col-span-2">
              <Skeleton height="280px" className="rounded-xl" />
            </div>
            <div className="col-span-3">
              <Skeleton height="360px" className="rounded-xl" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !kpi) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6">
        <ShieldAlert className="w-12 h-12 text-terracotta mb-4" />
        <p className="text-warm-800 font-medium">总览加载失败</p>
        <p className="text-sm text-warm-500 mt-2 max-w-md text-center">
          {error || '风控数据暂不可用（不会伪造演示 KPI）'}
        </p>
        <button
          type="button"
          onClick={() => void fetchOverview()}
          className="mt-4 h-9 px-4 rounded-lg bg-amber text-white text-sm"
        >
          重试
        </button>
      </div>
    );
  }

  const highRiskEnts = [...warnings].sort(
    (a, b) => (a.overall_score || 0) - (b.overall_score || 0),
  );
  const visibleEnts = showAllAlerts ? highRiskEnts : highRiskEnts.slice(0, TOP_N);
  const totalHigh = Math.max(topWarningsTotal, kpi.high_risk_count, highRiskEnts.length);
  const conclusion =
    kpi.conclusion ||
    `全库样本 ${kpi.sample_count} 家，高风险 ${kpi.high_risk_count} 家，活跃预警 ${kpi.warning_count} 家。`;

  const customerBar = industryBarData(industryProfiles, 'customer_concentration');
  const vatBurdenBar = industryBarData(industryProfiles, 'vat_burden');

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1100px] mx-auto p-6 space-y-5">
        {/* 标题：一行主结论入口 */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-lg font-bold text-warm-800">风险态势</h1>
            <p className="text-xs text-warm-400 mt-0.5">先看全局结论，再下钻异常 TopN</p>
          </div>
          <button
            type="button"
            onClick={() => navigate('/research')}
            className="h-9 px-4 rounded-lg text-xs font-medium bg-amber text-white hover:bg-amber/90 transition-colors"
          >
            去风险研判
          </button>
        </div>

        {/* 全局结论层 */}
        <motion.div custom={0} variants={fadeUp} initial="hidden" animate="visible">
          <div className="rounded-xl border border-amber/30 bg-amber/5 px-5 py-4">
            <p className="text-[11px] font-semibold text-amber uppercase tracking-wider mb-1.5">
              全局结论
            </p>
            <p className="text-[14px] leading-relaxed text-warm-800">{conclusion}</p>
          </div>
        </motion.div>

        {/* KPI */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard icon={Building2} label="匿名样本" value={kpi.sample_count} color="bg-blue-500" index={1} />
          <KpiCard icon={ShieldAlert} label="高风险" value={kpi.high_risk_count} color="bg-red-500" index={2} />
          <KpiCard icon={Bell} label="活跃预警" value={kpi.warning_count} color="bg-orange-500" index={3} />
          <KpiCard
            icon={BarChart3}
            label="样本均分"
            value={kpi.avg_score.toFixed(1)}
            color="bg-amber-500"
            index={4}
          />
        </div>

        {/* 主内容：分布 + 异常 TopN */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
          <div className="lg:col-span-2">
            <motion.div custom={5} variants={fadeUp} initial="hidden" animate="visible">
              <div className="bg-white rounded-xl border border-warm-200 shadow-sm p-5">
                <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider mb-3">
                  风险等级分布
                </p>
                {riskDistribution.length > 0 ? (
                  <div style={{ width: '100%', height: 260, flexShrink: 0, marginTop: -8 }}>
                    <PieChart data={riskDistribution} height={260} innerRadius="50%" centerY="38%" />
                  </div>
                ) : (
                  <p className="text-xs text-warm-400 text-center py-8">暂无数据</p>
                )}
              </div>
            </motion.div>
          </div>

          <motion.div
            custom={6}
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            className="lg:col-span-3"
          >
            <div className="bg-white rounded-xl border border-warm-200 shadow-sm flex flex-col">
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-warm-100">
                <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider">
                  异常企业 Top{Math.min(TOP_N, Math.max(totalHigh, 1))}
                </p>
                <span className="text-[11px] text-warm-300">
                  {showAllAlerts ? `已展开 ${highRiskEnts.length}` : `共 ${totalHigh}`} 家高风险
                </span>
              </div>
              <div className="overflow-y-auto max-h-[380px]">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-warm-100 bg-warm-50/50">
                      <th className="text-left text-[11px] font-medium text-warm-400 py-2.5 pl-4 pr-2">
                        企业
                      </th>
                      <th className="text-left text-[11px] font-medium text-warm-400 py-2.5 px-2">
                        行业
                      </th>
                      <th className="text-right text-[11px] font-medium text-warm-400 py-2.5 px-2">
                        评分
                      </th>
                      <th className="text-center text-[11px] font-medium text-warm-400 py-2.5 px-2">
                        等级
                      </th>
                      <th className="py-2.5 pr-4 pl-2 w-6" />
                    </tr>
                  </thead>
                  <tbody>
                    {visibleEnts.length > 0 ? (
                      visibleEnts.map((ent) => (
                        <AlertRow
                          key={ent.enterprise_id}
                          ent={ent}
                          onClick={() => navigate(`/enterprise/${ent.enterprise_id}`)}
                        />
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} className="py-12 text-center text-sm text-warm-400">
                          当前无高风险企业
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {totalHigh > TOP_N && (
                <div className="px-5 py-3 border-t border-warm-100 flex justify-center">
                  {showAllAlerts ? (
                    <button
                      type="button"
                      onClick={() => collapseAlerts()}
                      className="text-xs text-warm-500 hover:text-amber transition-colors"
                    >
                      收起，只看 Top{TOP_N}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void expandAllAlerts()}
                      disabled={isExpanding}
                      className="inline-flex items-center gap-1.5 text-xs text-amber hover:text-amber-dark transition-colors disabled:opacity-50"
                    >
                      {isExpanding ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <ChevronDown size={12} />
                      )}
                      查看全部（{totalHigh}）
                    </button>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        </div>

        {/* 行业对标：默认折叠 */}
        <div className="rounded-xl border border-warm-200 bg-white shadow-sm overflow-hidden">
          <button
            type="button"
            onClick={() => setShowBench((v) => !v)}
            className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-warm-50/60 transition-colors"
          >
            <span className="text-[13px] font-medium text-warm-700">行业对标（次级）</span>
            <ChevronDown
              size={16}
              className={`text-warm-400 transition-transform ${showBench ? 'rotate-180' : ''}`}
            />
          </button>
          {showBench && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 px-5 pb-5 border-t border-warm-100 pt-4">
              <div>
                <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider mb-2">
                  各行业平均客户集中度
                </p>
                {customerBar.categories.length > 0 ? (
                  <BarChart data={customerBar} horizontal height={240} />
                ) : (
                  <p className="text-xs text-warm-400 text-center py-8">暂无数据</p>
                )}
              </div>
              <div>
                <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider mb-2">
                  各行业平均增值税税负率
                </p>
                {vatBurdenBar.categories.length > 0 ? (
                  <BarChart data={vatBurdenBar} horizontal height={240} />
                ) : (
                  <p className="text-xs text-warm-400 text-center py-8">暂无数据</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* 指标字典：默认折叠 */}
        <div className="rounded-xl border border-warm-200 bg-white shadow-sm overflow-hidden">
          <button
            type="button"
            onClick={() => setShowDict((v) => !v)}
            className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-warm-50/60 transition-colors"
          >
            <span className="text-[13px] font-medium text-warm-700">指标字典</span>
            <ChevronDown
              size={16}
              className={`text-warm-400 transition-transform ${showDict ? 'rotate-180' : ''}`}
            />
          </button>
          {showDict && (
            <div className="px-3 pb-3 border-t border-warm-100">
              <MetricDictionary />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
