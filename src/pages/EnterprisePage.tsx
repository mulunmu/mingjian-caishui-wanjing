import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Building2,
  FileText,
  MessageSquare,
  Shield,
  TrendingDown,
  AlertTriangle,
} from 'lucide-react';
import { riskApi } from '@/api/risk';
import { reportApi } from '@/api/report';
import { translateSignal } from '@/api/overview';
import type { EnterpriseProfileResponse, PeerGroupPosition } from '@/types/risk';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import RadarChart from '@/components/charts/RadarChart';
import Skeleton from '@/components/ui/Skeleton';
import Divider from '@/components/ui/Divider';
import useChatStore from '@/stores/chatStore';

/* ── 维度标签颜色 ── */
const DIM_COLORS: Record<string, string> = {
  tax_health: 'text-blue-600',
  authenticity: 'text-emerald-600',
  industry: 'text-purple-600',
  legal: 'text-amber-600',
  finance: 'text-cyan-600',
};

/* ── 综合分颜色 ── */
function scoreColor(score: number): string {
  if (score >= 80) return 'text-emerald-600';
  if (score >= 60) return 'text-amber-600';
  if (score >= 40) return 'text-orange-500';
  return 'text-red-600';
}

/* ── 风险等级 → Badge level ── */
function riskBadgeLevel(risk: string): 'high' | 'medium' | 'low' {
  if (risk.includes('高')) return 'high';
  if (risk.includes('中')) return 'medium';
  return 'low';
}

/* ── 偏差颜色 ── */
function deviationColor(d: number): string {
  if (d <= -10) return 'text-red-600';
  if (d < 0) return 'text-amber-600';
  return 'text-emerald-600';
}

/* ── 同业基准定位表 ── */
function BenchmarkTable({ groups }: { groups: Record<string, PeerGroupPosition> }) {
  const rows = [
    { key: 'industry', ...groups.industry },
    { key: 'province', ...groups.province },
    { key: 'scale', ...groups.scale },
  ];

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-warm-200">
          <th className="text-left py-2 text-warm-500 font-medium">对比维度</th>
          <th className="text-left py-2 text-warm-500 font-medium">值</th>
          <th className="text-right py-2 text-warm-500 font-medium">排名</th>
          <th className="text-right py-2 text-warm-500 font-medium">分位</th>
          <th className="text-right py-2 text-warm-500 font-medium">偏差</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key} className="border-b border-warm-100 last:border-0">
            <td className="py-2.5 text-warm-700 font-medium">{r.label}</td>
            <td className="py-2.5 text-warm-600">{r.value || '-'}</td>
            <td className="py-2.5 text-right text-warm-700">
              {r.rank}/{r.peer_total}
            </td>
            <td className="py-2.5 text-right text-warm-600">
              {r.percentile.toFixed(1)}分位
            </td>
            <td className={`py-2.5 text-right font-semibold ${deviationColor(r.deviation)}`}>
              {r.deviation > 0 ? '+' : ''}
              {r.deviation.toFixed(1)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ── 主页面 ── */
export default function EnterprisePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<EnterpriseProfileResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [reportBusy, setReportBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchData = async () => {
    if (!id) return;
    setIsLoading(true);
    try {
      const res = await riskApi.getEnterpriseProfile(id);
      setData(res);
    } catch {
      setData(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleEnterpriseReport = async () => {
    if (!id) return;
    setReportBusy(true);
    setActionError(null);
    try {
      const res = await reportApi.enterprise(id);
      const reportId = (res as { report_id?: string }).report_id;
      if (reportId) {
        navigate(`/report?highlight=${encodeURIComponent(reportId)}`);
      } else {
        navigate('/report');
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '个体报告生成失败');
    } finally {
      setReportBusy(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [id]);

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto space-y-4">
          <Skeleton height="32px" width="200px" />
          <Skeleton height="120px" className="rounded-xl" />
          <div className="grid grid-cols-2 gap-4">
            <Skeleton height="360px" className="rounded-xl" />
            <Skeleton height="360px" className="rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 text-sm text-warm-500 hover:text-warm-700 transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            返回
          </button>
          <Card>
            <div className="flex flex-col items-center py-12">
              <AlertTriangle size={48} className="text-warm-300 mb-3" />
              <p className="text-warm-500">未找到该企业数据</p>
            </div>
          </Card>
        </div>
      </div>
    );
  }

  const { profile: p, peer_benchmark: bench } = data;
  const dims = p.dimensions;
  const dimDetails = p.dimension_details;

  // 雷达图数据
  const radarData = {
    indicators: [
      { name: `税务健康(${((dimDetails.tax_health?.weight || 0.25) * 100).toFixed(0)}%)`, max: 100 },
      { name: `经营真实性(${((dimDetails.authenticity?.weight || 0.25) * 100).toFixed(0)}%)`, max: 100 },
      { name: `行业地位(${((dimDetails.industry?.weight || 0.2) * 100).toFixed(0)}%)`, max: 100 },
      { name: `法律合规(${((dimDetails.legal?.weight || 0.15) * 100).toFixed(0)}%)`, max: 100 },
      { name: `财务健康(${((dimDetails.finance?.weight || 0.15) * 100).toFixed(0)}%)`, max: 100 },
    ],
    values: [
      dims.tax_health,
      dims.authenticity,
      dims.industry,
      dims.legal,
      dims.finance,
    ],
  };

  // 归因负向因素
  const negativeFactors: { item: string; deduction: number; dimLabel: string }[] = [];
  for (const [key, attr] of Object.entries(p.attribution?.dimensions || {})) {
    const label = attr.label || key;
    for (const neg of attr.negative || []) {
      negativeFactors.push({ item: neg.item, deduction: neg.deduction, dimLabel: label });
    }
  }
  negativeFactors.sort((a, b) => b.deduction - a.deduction);

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto space-y-5">
        {/* 返回 */}
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 text-sm text-warm-500 hover:text-warm-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          返回概览
        </button>
        {actionError && (
          <p className="text-sm text-terracotta">{actionError}</p>
        )}

        {/* ── 顶部标题栏 ── */}
        <Card className="!p-0">
          <div className="flex items-center justify-between p-5">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center">
                <Building2 size={24} className="text-amber-600" />
              </div>
              <div>
                <p className="text-xs text-warm-400 font-mono">
                  ANONYMOUS SAMPLE #{p.enterprise_id.slice(0, 8)}
                </p>
                <h1 className="text-xl font-bold text-warm-800 mt-0.5">
                  {p.display_label}
                </h1>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-sm text-warm-500">
                    {p.industry_l1 || '未知'} · {p.province || '未知'}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className={`text-3xl font-bold ${scoreColor(p.overall_score)}`}>
                  {p.overall_score.toFixed(1)}
                </p>
                <Badge level={riskBadgeLevel(p.risk_level)}>{p.risk_level}</Badge>
              </div>
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={() => {
                    useChatStore.getState().setEnterpriseId(p.enterprise_id);
                    navigate('/');
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                    bg-amber-500 text-white hover:bg-amber-600 transition-colors"
                >
                  <MessageSquare size={13} />
                  深入评估
                </button>
                <button
                  type="button"
                  disabled={reportBusy}
                  onClick={() => void handleEnterpriseReport()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                    border border-warm-300 text-warm-600 hover:bg-warm-50 transition-colors disabled:opacity-50"
                >
                  <FileText size={13} />
                  {reportBusy ? '生成中…' : '生成个体报告'}
                </button>
              </div>
            </div>
          </div>
        </Card>

        {/* ── 五维评估 + 同业基准定位 ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* 左：五维雷达 */}
          <Card>
            <h3 className="text-sm font-semibold text-warm-700 mb-1">五维评估</h3>
            <RadarChart data={radarData} height={300} />
            {/* 维度分数列表 */}
            <div className="grid grid-cols-5 gap-2 mt-2">
              {(['tax_health', 'authenticity', 'industry', 'legal', 'finance'] as const).map(
                (key) => (
                  <div key={key} className="text-center">
                    <p className={`text-lg font-bold ${DIM_COLORS[key] || 'text-warm-700'}`}>
                      {dims[key].toFixed(0)}
                    </p>
                    <p className="text-[10px] text-warm-400">
                      {dimDetails[key]?.label || key}
                    </p>
                  </div>
                ),
              )}
            </div>
          </Card>

          {/* 右：同业基准定位 */}
          <Card>
            <h3 className="text-sm font-semibold text-warm-700 mb-1">同业基准定位</h3>
            <p className="text-xs text-warm-400 mb-4">
              在同行业 / 同地区 / 同规模群体中的位置
            </p>
            {bench?.groups ? (
              <BenchmarkTable groups={bench.groups} />
            ) : (
              <p className="text-sm text-warm-400">暂无基准数据</p>
            )}
          </Card>
        </div>

        {/* ── 风险成因 + 预警信号 ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* 左下：风险成因 */}
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <TrendingDown size={16} className="text-red-500" />
              <h3 className="text-sm font-semibold text-warm-700">风险成因</h3>
            </div>
            {negativeFactors.length > 0 ? (
              <div className="space-y-2">
                {negativeFactors.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-2 px-3 rounded-lg bg-red-50/50 border border-red-100"
                  >
                    <span className="text-sm text-warm-700">{f.item}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-warm-400">{f.dimLabel}</span>
                      <span className="text-sm font-semibold text-red-600">
                        -{f.deduction.toFixed(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col items-center py-6">
                <Shield size={32} className="text-emerald-300 mb-2" />
                <p className="text-sm text-warm-400">无显著风险成因</p>
              </div>
            )}
          </Card>

          {/* 右下：预警信号 */}
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle size={16} className="text-red-500" />
              <h3 className="text-sm font-semibold text-warm-700">预警信号</h3>
            </div>
            {p.warning_signals && p.warning_signals.length > 0 ? (
              <div className="space-y-2">
                {p.warning_signals.map((sig, i) => {
                  const info = translateSignal(sig);
                  return (
                    <div
                      key={i}
                      className="flex items-center gap-3 py-2.5 px-3 rounded-lg bg-red-50/50 border border-red-100"
                    >
                      <div className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
                      <span className="text-sm text-warm-700 flex-1">{info.label}</span>
                      <Badge level={info.level}>
                        {info.level === 'high' ? '高危' : info.level === 'medium' ? '中危' : '低危'}
                      </Badge>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex flex-col items-center py-6">
                <Shield size={32} className="text-emerald-300 mb-2" />
                <p className="text-sm text-warm-400">当前无预警信号</p>
              </div>
            )}
          </Card>
        </div>

        {/* ── 归因摘要 ── */}
        {p.attribution?.summary && (
          <Card>
            <h3 className="text-sm font-semibold text-warm-700 mb-2">评估摘要</h3>
            <p className="text-sm text-warm-600 leading-relaxed">{p.attribution.summary}</p>
          </Card>
        )}
      </div>
    </div>
  );
}
