import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Building2,
  ShieldAlert,
  Bell,
  BarChart3,
  ChevronRight,
} from 'lucide-react';
import useOverviewStore from '@/stores/overviewStore';
import MetricDictionary from '@/components/overview/MetricDictionary';
import Badge from '@/components/ui/Badge';
import Skeleton from '@/components/ui/Skeleton';
import PieChart from '@/components/charts/PieChart';
import BarChart from '@/components/charts/BarChart';
import type { WarningEnterprise, IndustryProfileItem } from '@/types/overview';

/* ── 入场 ── */
const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.04, duration: 0.28, ease: [0.4, 0, 0.2, 1] },
  }),
};

/* ── 行业画像对标：0-1 → %，剔除弃权（null/0）行业，避免把源缺失当 0 拉低对标 ── */
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

/* ── KPI 卡 ── */
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
      <div className="bg-white rounded-xl border border-warm-200 px-4 py-3 flex items-center gap-3 shadow-sm">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={18} className="text-white" />
        </div>
        <div>
          <p className="text-[11px] text-warm-400 leading-none">{label}</p>
          <p className="text-xl font-bold text-warm-800 leading-tight mt-0.5">{value}</p>
        </div>
      </div>
    </motion.div>
  );
}

/* ── 高风险企业行 ── */
function AlertRow({ ent, onClick }: { ent: WarningEnterprise; onClick: () => void }) {
  const score = ent.overall_score ?? 0;
  return (
    <tr
      onClick={onClick}
      className="border-b border-warm-100 last:border-0 hover:bg-red-50/30 cursor-pointer transition-colors"
    >
      <td className="py-2 pl-4 pr-2">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
          <span className="text-[13px] text-warm-700 font-medium truncate max-w-[180px]">
            {ent.display_name || ent.enterprise_name || ent.display_label}
          </span>
        </div>
      </td>
      <td className="py-2 px-2 text-[13px] text-warm-500">{ent.industry_l1 || '-'}</td>
      <td className="py-2 px-2 text-right">
        <span className={`text-[13px] font-semibold tabular-nums ${score < 0 ? 'text-red-600' : 'text-warm-700'}`}>
          {score.toFixed(1)}
        </span>
      </td>
      <td className="py-2 px-2 text-center">
        <Badge level="high">高风险</Badge>
      </td>
      <td className="py-2 pr-4 pl-2 w-6 text-right">
        <ChevronRight size={13} className="text-warm-300 inline" />
      </td>
    </tr>
  );
}

/* ── 主页面 ── */
export default function OverviewPage() {
  const navigate = useNavigate();
  const { kpi, riskDistribution, industryProfiles, warnings, isLoading, error, fetchOverview } = useOverviewStore();

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="max-w-[1200px] mx-auto space-y-4">
          <Skeleton height="32px" width="180px" />
          <div className="grid grid-cols-4 gap-3">
            {[1, 2, 3, 4].map((i) => <Skeleton key={i} height="64px" className="rounded-xl" />)}
          </div>
          <div className="grid grid-cols-5 gap-4">
            <div className="col-span-2 space-y-4">
              <Skeleton height="280px" className="rounded-xl" />
              <Skeleton height="200px" className="rounded-xl" />
            </div>
            <div className="col-span-3">
              <Skeleton height="480px" className="rounded-xl" />
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

  const highRiskEnts = [...warnings]
    .filter((w) => (w.risk_level || '').includes('高'))
    .sort((a, b) => (a.overall_score || 0) - (b.overall_score || 0));

  const customerBar = industryBarData(industryProfiles, 'customer_concentration');
  const vatBurdenBar = industryBarData(industryProfiles, 'vat_burden');

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-[1200px] mx-auto p-6 space-y-4">

        {/* ── 标题 ── */}
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-lg font-bold text-warm-800">企业风险监测看板</h1>
            <p className="text-xs text-warm-400 mt-0.5">实时监控全域税务风险态势</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="h-8 px-3 rounded-lg text-xs font-medium bg-amber text-white hover:bg-amber/90 transition-colors"
            >
              深入评估
            </button>
            <button
              type="button"
              onClick={() => navigate('/risk/fraud')}
              className="h-8 px-3 rounded-lg text-xs font-medium border border-warm-300 text-warm-600 hover:bg-warm-50 transition-colors"
            >
              反欺诈
            </button>
            <button
              type="button"
              onClick={() => navigate('/risk/authenticity')}
              className="h-8 px-3 rounded-lg text-xs font-medium border border-warm-300 text-warm-600 hover:bg-warm-50 transition-colors"
            >
              真实性
            </button>
            <p className="text-[11px] text-warm-300 ml-1">
              {kpi.sample_count} 家样本 · 均分 {kpi.avg_score.toFixed(1)}
            </p>
          </div>
        </div>

        {/* ── KPI ── */}
        <div className="grid grid-cols-4 gap-3">
          <KpiCard icon={Building2} label="匿名样本" value={kpi.sample_count} color="bg-blue-500" index={0} />
          <KpiCard icon={ShieldAlert} label="高风险" value={kpi.high_risk_count} color="bg-red-500" index={1} />
          <KpiCard icon={Bell} label="活跃预警" value={kpi.warning_count} color="bg-orange-500" index={2} />
          <KpiCard icon={BarChart3} label="样本均分" value={kpi.avg_score.toFixed(1)} color="bg-amber-500" index={3} />
        </div>

        {/* ── 主内容区 ── */}
        <div className="grid grid-cols-5 gap-4">

          {/* 左侧（2/5）：风险等级分布 */}
          <div className="col-span-2 space-y-4">
            {/* 风险等级分布 */}
            <motion.div custom={4} variants={fadeUp} initial="hidden" animate="visible">
              <div className="bg-white rounded-xl border border-warm-200 shadow-sm p-4">
                <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider mb-2">
                  Distribution · 风险等级分布
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

          {/* 右侧（3/5）：高风险信号流 */}
          <motion.div custom={6} variants={fadeUp} initial="hidden" animate="visible" className="col-span-3">
            <div className="bg-white rounded-xl border border-warm-200 shadow-sm flex flex-col">
              {/* 头 */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-warm-100">
                <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider">
                  Alerts · 高风险信号流
                </p>
                <span className="text-[11px] text-warm-300">
                  共 {highRiskEnts.length} 家
                </span>
              </div>
              {/* 表 */}
              <div className="overflow-y-auto max-h-[420px]">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-warm-100 bg-warm-50/50">
                      <th className="text-left text-[11px] font-medium text-warm-400 py-2 pl-4 pr-2">企业</th>
                      <th className="text-left text-[11px] font-medium text-warm-400 py-2 px-2">行业</th>
                      <th className="text-right text-[11px] font-medium text-warm-400 py-2 px-2">评分</th>
                      <th className="text-center text-[11px] font-medium text-warm-400 py-2 px-2">等级</th>
                      <th className="py-2 pr-4 pl-2 w-6" />
                    </tr>
                  </thead>
                  <tbody>
                    {highRiskEnts.length > 0 ? (
                      highRiskEnts.map((ent) => (
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
            </div>
          </motion.div>
        </div>

        {/* ── 行业画像对标（横向条形图） ── */}
        <div className="grid grid-cols-2 gap-4">
          <motion.div custom={7} variants={fadeUp} initial="hidden" animate="visible">
            <div className="bg-white rounded-xl border border-warm-200 shadow-sm p-4">
              <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider mb-1">
                Benchmark · 各行业平均客户集中度
              </p>
              {customerBar.categories.length > 0 ? (
                <BarChart data={customerBar} horizontal height={260} />
              ) : (
                <p className="text-xs text-warm-400 text-center py-8">暂无数据</p>
              )}
            </div>
          </motion.div>
          <motion.div custom={8} variants={fadeUp} initial="hidden" animate="visible">
            <div className="bg-white rounded-xl border border-warm-200 shadow-sm p-4">
              <p className="text-[11px] font-semibold text-warm-400 uppercase tracking-wider mb-1">
                Benchmark · 各行业平均增值税税负率
              </p>
              {vatBurdenBar.categories.length > 0 ? (
                <BarChart data={vatBurdenBar} horizontal height={260} />
              ) : (
                <p className="text-xs text-warm-400 text-center py-8">暂无数据</p>
              )}
            </div>
          </motion.div>
        </div>

        {/* ── 指标字典 ── */}
        <MetricDictionary />

      </div>
    </div>
  );
}
