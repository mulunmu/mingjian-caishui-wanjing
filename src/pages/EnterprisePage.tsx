import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  BellRing,
  Building2,
  FileText,
  MessageSquare,
  Shield,
  TrendingDown,
  AlertTriangle,
} from 'lucide-react';
import { riskApi } from '@/api/risk';
import { reportApi } from '@/api/report';
import { subscriptionApi } from '@/api/subscription';
import { translateSignal } from '@/api/overview';
import { isSubscriber, needsUpgrade } from '@/utils/plan';
import type {
  AnomalySignal,
  EnterpriseProfileResponse,
  FinancialProfile,
  InvoiceProfile,
  PeerGroupPosition,
  TaxProfile,
  TopItem,
} from '@/types/risk';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import UpgradeModal from '@/components/ui/UpgradeModal';
import RadarChart from '@/components/charts/RadarChart';
import BarChart from '@/components/charts/BarChart';
import PieChart from '@/components/charts/PieChart';
import Skeleton from '@/components/ui/Skeleton';
import Divider from '@/components/ui/Divider';
import useChatStore from '@/stores/chatStore';
import useAuthStore from '@/stores/authStore';

/* ── 维度标签颜色 ── */
const DIM_COLORS: Record<string, string> = {
  tax_health: 'text-blue-600',
  authenticity: 'text-emerald-600',
  invoice: 'text-rose-600',
  industry: 'text-purple-600',
  legal: 'text-amber-600',
  finance: 'text-cyan-600',
};

/* ── 百分比/份额格式化 ── */
function pct(v: number | undefined | null): string {
  const n = Number(v ?? 0);
  return `${(n * 100).toFixed(1)}%`;
}

/* ── 脱敏对手方名截断 ── */
function shortName(name: string | undefined | null): string {
  const n = (name || '').trim();
  if (!n) return '未具名';
  return n.length > 12 ? `${n.slice(0, 12)}…` : n;
}

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

/* ── 画像统计卡 ── */
function StatCard({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'default' | 'warn' | 'danger';
}) {
  const toneCls =
    tone === 'danger'
      ? 'text-red-600'
      : tone === 'warn'
        ? 'text-amber-600'
        : 'text-warm-800';
  return (
    <div className="rounded-xl border border-warm-200 bg-warm-50/40 p-3">
      <p className="text-xs text-warm-400">{label}</p>
      <p className={`text-lg font-bold mt-1 ${toneCls}`}>{value}</p>
      {hint && <p className="text-[10px] text-warm-400 mt-0.5">{hint}</p>}
    </div>
  );
}

/* ── TOP-N 柱状/饼图数据 ── */
function topBarData(items: TopItem[]): { categories: string[]; values: number[] } {
  return {
    categories: items.map((it) => shortName(it.name)),
    values: items.map((it) => Number(it.share ?? 0) * 100),
  };
}

/* ── 发票画像区块 ── */
function InvoiceProfileSection({ p }: { p: InvoiceProfile }) {
  const customerData = topBarData(p.top_customers || []);
  const supplierData = topBarData(p.top_suppliers || []);
  const categoryData = (p.top_categories || []).map((it) => ({
    name: shortName(it.name),
    value: Number(it.share ?? 0) * 100,
  }));

  return (
    <Card>
      <div className="flex items-center gap-2 mb-4">
        <Shield size={16} className="text-rose-500" />
        <h3 className="text-sm font-semibold text-warm-700">发票画像</h3>
        <span className="text-xs text-warm-400">进销项 · 集中度 · 凭证质量</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
        <StatCard label="客户集中度" value={pct(p.top_customer_share)} hint={`客户 ${p.customer_count} 家`} />
        <StatCard label="供应商集中度" value={pct(p.top_supplier_share)} hint={`供应商 ${p.supplier_count} 家`} />
        <StatCard label="品目集中度" value={pct(p.top_category_share)} hint={`品目 ${p.category_count} 类`} />
        <StatCard
          label="作废发票"
          value={`${p.void_invoice_cnt} 笔`}
          tone={p.void_invoice_cnt > 0 ? 'warn' : 'default'}
        />
        <StatCard
          label="单价离散(最高/均价)"
          value={p.avg_unit_price > 0 ? (p.max_unit_price / p.avg_unit_price).toFixed(1) : '—'}
          tone={p.avg_unit_price > 0 && p.max_unit_price / p.avg_unit_price > 100000 ? 'danger' : 'default'}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <p className="text-xs text-warm-400 mb-2">客户 TOP5（金额份额）</p>
          {customerData.values.length ? (
            <BarChart data={{ categories: customerData.categories, values: customerData.values, title: '客户 TOP5' }} horizontal height={240} />
          ) : (
            <p className="text-sm text-warm-400 py-6 text-center">暂无客户明细</p>
          )}
        </div>
        <div>
          <p className="text-xs text-warm-400 mb-2">供应商 TOP5（金额份额）</p>
          {supplierData.values.length ? (
            <BarChart data={{ categories: supplierData.categories, values: supplierData.values, title: '供应商 TOP5' }} horizontal height={240} />
          ) : (
            <p className="text-sm text-warm-400 py-6 text-center">暂无供应商明细</p>
          )}
        </div>
        <div>
          <p className="text-xs text-warm-400 mb-2">品目 TOP5（金额份额）</p>
          {categoryData.length ? (
            <PieChart data={categoryData} title="品目 TOP5" height={240} />
          ) : (
            <p className="text-sm text-warm-400 py-6 text-center">暂无品目明细</p>
          )}
        </div>
      </div>
    </Card>
  );
}

/* ── 税务画像区块 ── */
function TaxProfileSection({ p }: { p: TaxProfile }) {
  return (
    <Card>
      <div className="flex items-center gap-2 mb-4">
        <Shield size={16} className="text-blue-500" />
        <h3 className="text-sm font-semibold text-warm-700">税务画像</h3>
        <span className="text-xs text-warm-400">税负 · 申报诚信 · 社保 · 变更</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <StatCard
          label="增值税税负率"
          value={pct(p.vat_burden)}
          tone={p.vat_burden > 0 && p.vat_burden < 0.005 ? 'danger' : 'default'}
        />
        <StatCard
          label="所得税税负率"
          value={pct(p.income_tax_burden)}
          tone={p.income_tax_burden > 0 && p.income_tax_burden < 0.001 ? 'danger' : 'default'}
        />
        <StatCard label="申报更正次数" value={`${p.correction_times} 次`} tone={p.correction_times >= 80 ? 'warn' : 'default'} />
        <StatCard label="社保缴费人数" value={`${p.social_headcount} 人`} />
        <StatCard label="滞纳金/罚款" value={`${p.tax_late_penalty_cnt} 笔`} tone={p.tax_late_penalty_cnt > 0 ? 'warn' : 'default'} />
        <StatCard label="变更登记次数" value={`${p.change_cnt} 次`} tone={p.change_cnt >= 15 ? 'warn' : 'default'} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mt-3">
        <StatCard label="已缴税款合计" value={`${(p.total_tax_paid / 10000).toFixed(1)} 万`} />
        <StatCard label="滞纳金/罚款额" value={`${(p.tax_late_penalty_amount / 10000).toFixed(1)} 万`} />
        <StatCard label="银税互动贷款余额" value={`${(p.tax_loan_balance / 10000).toFixed(1)} 万`} />
        <StatCard label="减免所得税额" value={`${(p.tax_preference_amount / 10000).toFixed(1)} 万`} />
        <StatCard label="研发费用" value={`${(p.rd_expense / 10000).toFixed(1)} 万`} />
        <StatCard label="第一大投资方比例" value={pct(p.top_investor_share)} hint={p.is_high_tech ? '高新技术企业' : undefined} />
      </div>
    </Card>
  );
}

/* ── 财务画像区块 ── */
type FinField = keyof FinancialProfile['ratios'];
interface FinRatioDef {
  field: FinField;
  label: string;
  isPct: boolean;
  warnDir: 'gt' | 'lt' | null;
  thr: number | null;
}
const FIN_GROUPS: { name: string; ratios: FinRatioDef[] }[] = [
  {
    name: '偿债能力',
    ratios: [
      { field: 'debt_ratio', label: '资产负债率', isPct: true, warnDir: 'gt', thr: 0.7 },
      { field: 'current_ratio', label: '流动比率', isPct: false, warnDir: 'lt', thr: 1.0 },
      { field: 'quick_ratio', label: '速动比率', isPct: false, warnDir: 'lt', thr: 0.5 },
    ],
  },
  {
    name: '营运能力',
    ratios: [
      { field: 'receivables_turnover', label: '应收周转', isPct: false, warnDir: 'lt', thr: 2.0 },
      { field: 'inventory_turnover', label: '存货周转', isPct: false, warnDir: 'lt', thr: 2.0 },
      { field: 'asset_turnover', label: '总资产周转', isPct: false, warnDir: null, thr: null },
    ],
  },
  {
    name: '盈利能力',
    ratios: [
      { field: 'gross_margin', label: '毛利率', isPct: true, warnDir: 'lt', thr: 0.1 },
      { field: 'net_margin', label: '净利率', isPct: true, warnDir: 'lt', thr: 0 },
      { field: 'roe', label: '净资产收益率', isPct: true, warnDir: 'lt', thr: 0 },
      { field: 'roa', label: '总资产收益率', isPct: true, warnDir: null, thr: null },
    ],
  },
  {
    name: '成长能力',
    ratios: [
      { field: 'revenue_yoy', label: '营收同比', isPct: true, warnDir: 'lt', thr: -0.2 },
      { field: 'profit_yoy', label: '净利润同比', isPct: true, warnDir: null, thr: null },
    ],
  },
];

function finFmt(v: number, isPct: boolean): string {
  if (!v) return '无数据';
  return isPct ? `${(v * 100).toFixed(1)}%` : v.toFixed(2);
}

function finRating(r: FinRatioDef, v: number): '预警' | '达标' | '无数据' {
  if (!v) return '无数据';
  if (r.warnDir === 'gt' && r.thr != null && v > r.thr) return '预警';
  if (r.warnDir === 'lt' && r.thr != null && v < r.thr) return '预警';
  return '达标';
}

function finTone(rating: string): string {
  if (rating === '预警') return 'text-red-600';
  if (rating === '达标') return 'text-emerald-600';
  return 'text-warm-400';
}

function fmtWan(v: number): string {
  if (!v) return '—';
  return `${(v / 10000).toFixed(1)} 万`;
}

function FinancialProfileSection({ p }: { p: FinancialProfile }) {
  const statements: { title: string; rows: [string, number][] }[] = [
    {
      title: '资产负债表',
      rows: [
        ['资产总计', p.balance_sheet.total_assets],
        ['负债合计', p.balance_sheet.total_liab],
        ['流动资产合计', p.balance_sheet.current_assets],
        ['流动负债合计', p.balance_sheet.current_liab],
        ['货币资金', p.balance_sheet.cash_equiv],
        ['存货', p.balance_sheet.inventory],
        ['应收账款', p.balance_sheet.accounts_receivable],
        ['固定资产净额', p.balance_sheet.fixed_assets],
        ['短期借款', p.balance_sheet.short_loan],
        ['所有者权益合计', p.balance_sheet.owner_equity],
        ['未分配利润', p.balance_sheet.retained_earnings],
      ],
    },
    {
      title: '利润表',
      rows: [
        ['营业收入', p.income_statement.revenue],
        ['营业成本', p.income_statement.cost],
        ['税金及附加', p.income_statement.tax_surcharge],
        ['销售费用', p.income_statement.sell_expense],
        ['管理费用', p.income_statement.admin_expense],
        ['财务费用', p.income_statement.finance_expense],
        ['营业利润', p.income_statement.operating_profit],
        ['利润总额', p.income_statement.total_profit],
        ['所得税费用', p.income_statement.income_tax],
        ['净利润', p.income_statement.net_profit],
      ],
    },
    {
      title: '现金流量表',
      rows: [
        ['经营现金流净额', p.cash_flow.operating_cf],
        ['投资现金流净额', p.cash_flow.investing_cf],
        ['筹资现金流净额', p.cash_flow.financing_cf],
      ],
    },
  ];

  return (
    <Card>
      <div className="flex items-center gap-2 mb-4">
        <Shield size={16} className="text-cyan-500" />
        <h3 className="text-sm font-semibold text-warm-700">财务分析</h3>
        <span className="text-xs text-warm-400">
          三大报表 · 四能力比率{p.report_year ? ` · 报告期 ${p.report_year}` : ''}
        </span>
      </div>

      {/* 四能力比率 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        {FIN_GROUPS.map((g) => (
          <div key={g.name} className="rounded-xl border border-warm-200 bg-warm-50/40 p-3">
            <p className="text-xs font-semibold text-warm-500 mb-2">{g.name}</p>
            <div className="space-y-1.5">
              {g.ratios.map((r) => {
                const v = p.ratios[r.field];
                const rating = finRating(r, v);
                return (
                  <div key={r.field} className="flex items-center justify-between">
                    <span className="text-xs text-warm-500">{r.label}</span>
                    <span className="text-right">
                      <span className={`text-sm font-semibold tabular-nums ${finTone(rating)}`}>
                        {finFmt(v, r.isPct)}
                      </span>
                      <span className={`text-[10px] ml-1 ${finTone(rating)}`}>{rating}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* 杜邦分解 */}
      {p.dupont && (
        <div className="rounded-xl border border-cyan-200 bg-cyan-50/30 p-3 mb-5">
          <p className="text-xs font-semibold text-warm-600 mb-2">杜邦分解（净资产收益率 ROE）</p>
          {p.dupont.complete ? (
            <>
              <p className="text-sm text-warm-700 mb-2">
                <span className="font-bold tabular-nums text-cyan-700">{p.dupont.roe_disp}</span>
                <span className="mx-1 text-warm-400">=</span>
                {p.dupont.factors.map((f, i) => (
                  <span key={f.field}>
                    {i > 0 && <span className="mx-1 text-warm-400">×</span>}
                    <span className="text-warm-500">{f.label}</span>
                    <span className="tabular-nums font-semibold text-warm-700">{f.disp}</span>
                  </span>
                ))}
              </p>
              <div className="grid grid-cols-3 gap-3">
                {p.dupont.factors.map((f) => (
                  <div key={f.field} className="rounded-lg bg-white border border-warm-200 p-2 text-center">
                    <p className="text-[11px] text-warm-400">{f.dir}</p>
                    <p className="text-xs font-semibold text-warm-700 mt-0.5">{f.label}</p>
                    <p className="text-sm font-bold tabular-nums text-cyan-700 mt-0.5">
                      {f.disp ?? '无数据'}
                    </p>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-warm-400">因关键因子无数据（弃权），本期不做完整杜邦分解。</p>
          )}
        </div>
      )}

      {/* 三大报表 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {statements.map((s) => (
          <div key={s.title} className="rounded-xl border border-warm-200 p-3">
            <p className="text-xs font-semibold text-warm-600 mb-2">{s.title}</p>
            <table className="w-full text-xs">
              <tbody>
                {s.rows.map(([label, val]) => (
                  <tr key={label} className="border-b border-warm-100 last:border-0">
                    <td className="py-1.5 text-warm-500">{label}</td>
                    <td className="py-1.5 text-right text-warm-700 tabular-nums font-medium">
                      {fmtWan(val)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* ── 异动信号标签 → 徽标级别 ── */
const TAG_TONE: Record<AnomalySignal['tag'], { badge: 'high' | 'medium' | 'low'; dot: string }> = {
  高危: { badge: 'high', dot: 'bg-red-500' },
  新增: { badge: 'high', dot: 'bg-orange-500' },
  较上期恶化: { badge: 'medium', dot: 'bg-amber-500' },
  预警: { badge: 'medium', dot: 'bg-amber-400' },
};

/* ── 异动信号区块 ── */
function AnomalySignalsSection({ signals }: { signals: AnomalySignal[] }) {
  if (signals.length === 0) return null;
  const highCount = signals.filter((s) => s.level === 'high').length;
  return (
    <Card>
      <div className="flex items-center gap-2 mb-1">
        <BellRing size={16} className="text-orange-500" />
        <h3 className="text-sm font-semibold text-warm-700">异动信号</h3>
        <span className="text-xs text-warm-400">
          差异驱动 · 共 {signals.length} 条{highCount > 0 ? ` · 高危 ${highCount}` : ''}
        </span>
      </div>
      <p className="text-xs text-warm-400 mb-4">较上期恶化 / 新增事件，数据刷新后自动检出，可订阅推送。</p>
      <div className="space-y-2">
        {signals.map((s, i) => {
          const tone = TAG_TONE[s.tag] ?? { badge: 'medium' as const, dot: 'bg-warm-400' };
          return (
            <div
              key={i}
              className="flex items-start gap-3 py-2.5 px-3 rounded-lg border border-warm-200 bg-warm-50/30"
            >
              <div className={`w-2 h-2 rounded-full ${tone.dot} mt-1.5 flex-shrink-0`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-warm-800">
                  <Badge level={tone.badge}>{s.tag}</Badge>
                  <span className="ml-2">
                    [{s.category}] {s.title}
                  </span>
                </p>
                <p className="text-xs text-warm-500 mt-0.5">{s.evidence}</p>
                {s.advice && <p className="text-xs text-warm-600 mt-1 leading-relaxed">{s.advice}</p>}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
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
  const [subscribed, setSubscribed] = useState(false);
  const [subBusy, setSubBusy] = useState(false);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [upgradeFeature, setUpgradeFeature] = useState('个体深度报告');
  const user = useAuthStore((s) => s.user);
  const canSubscribe = !user || isSubscriber(user);

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

  const refreshSubscription = async () => {
    if (!id) return;
    try {
      const res = await subscriptionApi.list();
      setSubscribed((res.items || []).some((it) => it.enterprise_id === id));
    } catch {
      setSubscribed(false);
    }
  };

  const handleToggleSubscribe = async () => {
    if (!id || subBusy) return;
    setSubBusy(true);
    setActionError(null);
    try {
      if (subscribed) {
        await subscriptionApi.unsubscribe(id);
        setSubscribed(false);
      } else {
        await subscriptionApi.subscribe(id);
        setSubscribed(true);
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '订阅操作失败');
    } finally {
      setSubBusy(false);
    }
  };

  const handleEnterpriseReport = async () => {
    if (!id) return;
    if (needsUpgrade(user)) {
      setUpgradeFeature('个体深度报告');
      setShowUpgrade(true);
      return;
    }
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
    refreshSubscription();
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

  const {
    profile: p,
    peer_benchmark: bench,
    insights = [],
    invoice_profile: invoiceProfile,
    tax_profile: taxProfile,
    financial,
    anomaly_signals: anomalySignals = [],
  } = data;
  const dims = p.dimensions;
  const dimDetails = p.dimension_details;

  // 雷达图数据
  const radarData = {
    indicators: [
      { name: `税务健康(${((dimDetails.tax_health?.weight || 0.25) * 100).toFixed(0)}%)`, max: 100 },
      { name: `经营真实性(${((dimDetails.authenticity?.weight || 0.25) * 100).toFixed(0)}%)`, max: 100 },
      { name: `发票健康(${((dimDetails.invoice?.weight || 0.15) * 100).toFixed(0)}%)`, max: 100 },
      { name: `行业地位(${((dimDetails.industry?.weight || 0.2) * 100).toFixed(0)}%)`, max: 100 },
      { name: `法律合规(${((dimDetails.legal?.weight || 0.15) * 100).toFixed(0)}%)`, max: 100 },
      { name: `财务健康(${((dimDetails.finance?.weight || 0.15) * 100).toFixed(0)}%)`, max: 100 },
    ],
    values: [
      dims.tax_health,
      dims.authenticity,
      dims.invoice,
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
                  {p.display_label}
                </p>
                <h1 className="text-xl font-bold text-warm-800 mt-0.5">
                  {p.enterprise_name}
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
                    navigate('/research');
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                    bg-amber-500 text-white hover:bg-amber-600 transition-colors"
                >
                  <MessageSquare size={13} />
                  风险研判
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
                <button
                  type="button"
                  disabled={subBusy}
                  onClick={() => {
                    if (!canSubscribe) {
                      setUpgradeFeature('订阅异动推送');
                      setShowUpgrade(true);
                      return;
                    }
                    void handleToggleSubscribe();
                  }}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                    border transition-colors disabled:opacity-50 ${
                      subscribed
                        ? 'border-orange-300 bg-orange-50 text-orange-600 hover:bg-orange-100'
                        : 'border-warm-300 text-warm-600 hover:bg-warm-50'
                    }`}
                >
                  <BellRing size={13} />
                  {subBusy
                    ? '处理中…'
                    : !canSubscribe
                      ? '订阅异动（需升级）'
                      : subscribed
                        ? '已订阅异动'
                        : '订阅异动推送'}
                </button>
              </div>
            </div>
          </div>
        </Card>

        {/* ── 六维评估 + 同业基准定位 ── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* 左：六维雷达 */}
          <Card>
            <h3 className="text-sm font-semibold text-warm-700 mb-1">六维评估</h3>
            <RadarChart data={radarData} height={300} />
            {/* 维度分数列表 */}
            <div className="grid grid-cols-6 gap-2 mt-2">
              {(['tax_health', 'authenticity', 'invoice', 'industry', 'legal', 'finance'] as const).map(
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

        {/* ── 发票画像 + 税务画像 + 财务分析 ── */}
        {invoiceProfile && <InvoiceProfileSection p={invoiceProfile} />}
        {taxProfile && <TaxProfileSection p={taxProfile} />}
        {financial && <FinancialProfileSection p={financial} />}

        {/* ── 风险洞察（多指标联动） ── */}
        {insights.length > 0 && (
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <Shield size={16} className="text-amber-500" />
              <h3 className="text-sm font-semibold text-warm-700">风险洞察</h3>
              <span className="inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-medium bg-warm-100 text-warm-600 border-warm-200">
                风险识别 · 规则引擎
              </span>
              <span className="text-xs text-warm-400">多指标联动 · 共 {insights.length} 条</span>
            </div>
            <div className="space-y-2">
              {insights.map((ins, i) => {
                const high = ins.severity === '高危';
                return (
                  <div
                    key={i}
                    className={`flex items-start gap-3 py-2.5 px-3 rounded-lg border ${
                      high ? 'bg-red-50/50 border-red-100' : 'bg-amber-50/40 border-amber-100'
                    }`}
                  >
                    <Badge level={high ? 'high' : 'medium'}>{ins.severity}</Badge>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-warm-800">
                        <span className="text-xs text-warm-400 font-normal mr-2">
                          [{ins.category}]
                        </span>
                        {ins.title}
                      </p>
                      <p className="text-xs text-warm-500 mt-0.5">{ins.fact}</p>
                      {ins.advice && (
                        <p className="text-xs text-warm-600 mt-1 leading-relaxed">{ins.advice}</p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        )}

        {/* ── 异动信号（差异驱动） ── */}
        <AnomalySignalsSection signals={anomalySignals} />

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

      <UpgradeModal
        open={showUpgrade}
        onClose={() => setShowUpgrade(false)}
        feature={upgradeFeature}
      />
    </div>
  );
}
