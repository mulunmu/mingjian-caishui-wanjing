import { useState, useEffect } from 'react';
import { ArrowLeft, ArrowRight, Loader2, Sparkles, X, Building2, Search, AlertTriangle } from 'lucide-react';
import {
  REPORT_SCENARIOS,
  ENTERPRISE_SCENARIO,
  type ReportScenarioDef,
  type ScenarioMotif,
} from '@/constants/reportScenarios';
import { riskApi, type IndustryItem, type EnterpriseOption } from '@/api/risk';
import { reportApi } from '@/api/report';

/** 封面母题图形（与 PDF 封面 slice_report.html 同源） */
function Motif({ motif, accent }: { motif: ScenarioMotif; accent: string }) {
  if (motif === 'ledger') {
    return (
      <svg viewBox="0 0 120 120" width="40" height="40" aria-hidden>
        <g fill={accent}>
          <rect x="16" y="70" width="18" height="30" rx="3" />
          <rect x="51" y="50" width="18" height="50" rx="3" />
          <rect x="86" y="30" width="18" height="70" rx="3" />
        </g>
        <line x1="10" y1="106" x2="110" y2="106" stroke={accent} strokeWidth="3" />
      </svg>
    );
  }
  if (motif === 'seal') {
    return (
      <svg viewBox="0 0 120 120" width="40" height="40" aria-hidden>
        <circle cx="60" cy="60" r="44" fill="none" stroke={accent} strokeWidth="5" />
        <circle cx="60" cy="60" r="34" fill="none" stroke={accent} strokeWidth="1.5" opacity="0.5" />
        <path d="M44 62 L56 74 L78 48" fill="none" stroke={accent} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (motif === 'magnifier') {
    return (
      <svg viewBox="0 0 120 120" width="40" height="40" aria-hidden>
        <circle cx="52" cy="52" r="30" fill="none" stroke={accent} strokeWidth="6" />
        <circle cx="52" cy="52" r="8" fill={accent} />
        <line x1="74" y1="74" x2="100" y2="100" stroke={accent} strokeWidth="8" strokeLinecap="round" />
      </svg>
    );
  }
  if (motif === 'badge') {
    return (
      <svg viewBox="0 0 120 120" width="40" height="40" aria-hidden>
        <rect x="18" y="24" width="84" height="72" rx="8" fill="none" stroke={accent} strokeWidth="4" />
        <circle cx="44" cy="52" r="12" fill={accent} />
        <rect x="64" y="42" width="26" height="5" rx="2.5" fill={accent} opacity="0.7" />
        <rect x="64" y="52" width="18" height="5" rx="2.5" fill={accent} opacity="0.45" />
        <rect x="26" y="76" width="68" height="4" rx="2" fill={accent} opacity="0.35" />
      </svg>
    );
  }
  // compass（默认）
  return (
    <svg viewBox="0 0 120 120" width="40" height="40" aria-hidden>
      <circle cx="60" cy="60" r="46" fill="none" stroke={accent} strokeWidth="3" />
      <polygon points="60,22 70,60 60,98 50,60" fill={accent} />
      <polygon points="22,60 60,50 98,60 60,70" fill={accent} opacity="0.45" />
      <circle cx="60" cy="60" r="6" fill="#fff" />
    </svg>
  );
}

/** 向导偏好：范围（全部/行业/指定企业）+ 场景；真正传给后端（非占位）。 */
export interface WizardPrefs {
  scenarioKey: string;
  industry_l1?: string | null;
  enterprise_id?: string | null;
}

interface ReportWizardProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (scenario: ReportScenarioDef, prefs: WizardPrefs) => void;
  busy: boolean;
  error: string | null;
  /** 跳转对话定制（恢复「自由组合章节」本意入口） */
  onOpenCustom?: () => void;
}

const STEP_TITLES = ['选择范围', '选择场景', '确认生成'];

export default function ReportWizard({ open, onClose, onConfirm, busy, error, onOpenCustom }: ReportWizardProps) {
  const [step, setStep] = useState(0);
  const [scopeType, setScopeType] = useState<'all' | 'industry' | 'enterprise'>('all');
  const [industryL1, setIndustryL1] = useState<string | null>(null);
  const [industries, setIndustries] = useState<IndustryItem[]>([]);
  const [enterprises, setEnterprises] = useState<EnterpriseOption[]>([]);
  const [enterpriseId, setEnterpriseId] = useState<string | null>(null);
  const [enterpriseQuery, setEnterpriseQuery] = useState('');
  const [scenarioKey, setScenarioKey] = useState<string | null>(null);
  const [precheck, setPrecheck] = useState<{
    loading: boolean;
    ok: boolean | null;
    reason: string;
    sampleCount?: number;
  }>({ loading: false, ok: null, reason: '' });

  // 打开时只拉行业；企业清单按需搜索，避免全量 193 首屏卡顿（刀 2b）
  useEffect(() => {
    if (!open) return;
    riskApi
      .getIndustries()
      .then(setIndustries)
      .catch(() => setIndustries([]));
  }, [open]);

  // 企业搜索（防抖）：无关键字时仅拉前 20 条演示样例
  useEffect(() => {
    if (!open || scopeType !== 'enterprise') return;
    const t = setTimeout(() => {
      riskApi
        .getEnterprises(enterpriseQuery || undefined, 20)
        .then(setEnterprises)
        .catch(() => setEnterprises([]));
    }, 200);
    return () => clearTimeout(t);
  }, [enterpriseQuery, scopeType, open]);

  // 确认步：预校验样本/章节（生成前拦截空报告）
  useEffect(() => {
    if (!open || step !== 2 || !scenarioKey) {
      setPrecheck({ loading: false, ok: null, reason: '' });
      return;
    }
    let cancelled = false;
    setPrecheck({ loading: true, ok: null, reason: '' });
    const run = async () => {
      try {
        const res = await reportApi.validateWizard({
          scenario: scopeType === 'enterprise' ? undefined : scenarioKey,
          industry_l1: scopeType === 'industry' ? industryL1 || undefined : undefined,
          enterprise_id: scopeType === 'enterprise' ? enterpriseId || undefined : undefined,
        });
        if (cancelled) return;
        setPrecheck({
          loading: false,
          ok: !!res.ok,
          reason: res.reason || '',
          sampleCount: res.scope_sample_count,
        });
      } catch {
        if (cancelled) return;
        setPrecheck({
          loading: false,
          ok: false,
          reason: '预校验暂不可用，请稍后重试。',
        });
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [open, step, scenarioKey, scopeType, industryL1, enterpriseId]);

  if (!open) return null;

  const scenario =
    scopeType === 'enterprise'
      ? ENTERPRISE_SCENARIO
      : REPORT_SCENARIOS.find((s) => s.key === scenarioKey) || null;

  const reset = () => {
    setStep(0);
    setScopeType('all');
    setIndustryL1(null);
    setEnterpriseId(null);
    setEnterpriseQuery('');
    setScenarioKey(null);
    setPrecheck({ loading: false, ok: null, reason: '' });
  };

  const close = () => {
    reset();
    onClose();
  };

  const canNext =
    step === 0
      ? scopeType === 'all' ||
        (scopeType === 'industry' && !!industryL1) ||
        (scopeType === 'enterprise' && !!enterpriseId)
      : step === 1
        ? scopeType === 'enterprise' || !!scenarioKey
        : true;

  const confirm = () => {
    if (!scenario) return;
    if (precheck.ok === false) return;
    onConfirm(scenario, {
      scenarioKey: scopeType === 'enterprise' ? 'enterprise' : scenario.key,
      industry_l1: scopeType === 'industry' ? industryL1 : null,
      enterprise_id: scopeType === 'enterprise' ? enterpriseId : null,
    });
  };

  const selectedEnterprise = enterprises.find((e) => e.enterprise_id === enterpriseId) || null;
  const scopeText =
    scopeType === 'enterprise' && selectedEnterprise
      ? selectedEnterprise.display_name
      : scopeType === 'industry' && industryL1
        ? industryL1
        : '全部样本';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-warm-900/40"
      onClick={close}
    >
      <div
        className="relative w-[600px] max-w-[94vw] rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={close}
          className="absolute top-4 right-4 p-1 rounded text-warm-400 hover:bg-warm-100 transition-colors"
          title="关闭"
        >
          <X size={16} />
        </button>

        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={16} className="text-amber" />
          <h3 className="text-base font-semibold text-warm-800">报告生成向导</h3>
        </div>
        <p className="mb-2 text-xs text-warm-400">
          本向导是<strong className="font-medium text-warm-600">快捷模板</strong>
          （个体六维体检 / 全库·行业仅画像+预警），方便一键出标准报告。
        </p>
        <p className="mb-4 text-[11px] text-warm-500">
          <strong className="font-medium text-warm-600">定制本意</strong>
          在对话里：识别你的场景（财务/税务/发票/尽调…）再拼章节出报告——请用
          {onOpenCustom ? (
            <button
              type="button"
              onClick={() => {
                close();
                onOpenCustom();
              }}
              className="mx-1 text-amber underline underline-offset-2 hover:text-amber-dark"
            >
              AI 对话定制
            </button>
          ) : (
            <span className="mx-1 text-warm-600">「AI 定制报告」</span>
          )}
          。
        </p>

        {/* 步骤进度 */}
        <div className="mb-4">
          <div className="flex items-center gap-1 mb-1.5">
            {STEP_TITLES.map((t, i) => (
              <div key={t} className="flex-1">
                <div
                  className={`h-1.5 rounded-full ${i <= step ? 'bg-amber' : 'bg-warm-200'}`}
                />
              </div>
            ))}
          </div>
          <p className="text-[11px] text-warm-500">
            步骤 {step + 1} / {STEP_TITLES.length} · {STEP_TITLES[step]}
          </p>
        </div>

        {/* S1 范围 */}
        {step === 0 && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => {
                  setScopeType('all');
                  setScenarioKey(null);
                }}
                className={`flex items-start gap-2 rounded-xl border p-3 text-left transition-all ${
                  scopeType === 'all'
                    ? 'border-amber-400 bg-amber-50/50'
                    : 'border-warm-200 bg-white hover:border-amber-400 hover:bg-amber-50/30'
                }`}
              >
                <Building2 size={16} className="text-warm-400 mt-0.5" />
                <div>
                  <div className="text-sm font-medium text-warm-800">全部样本</div>
                  <p className="text-xs text-warm-500 mt-0.5">全库画像 + 预警</p>
                </div>
              </button>
              <button
                onClick={() => {
                  setScopeType('industry');
                  setScenarioKey(null);
                }}
                className={`flex items-start gap-2 rounded-xl border p-3 text-left transition-all ${
                  scopeType === 'industry'
                    ? 'border-amber-400 bg-amber-50/50'
                    : 'border-warm-200 bg-white hover:border-amber-400 hover:bg-amber-50/30'
                }`}
              >
                <Building2 size={16} className="text-warm-400 mt-0.5" />
                <div>
                  <div className="text-sm font-medium text-warm-800">指定行业</div>
                  <p className="text-xs text-warm-500 mt-0.5">行业画像 + 预警（同构）</p>
                </div>
              </button>
              <button
                onClick={() => {
                  setScopeType('enterprise');
                  setScenarioKey('enterprise');
                }}
                className={`flex items-start gap-2 rounded-xl border p-3 text-left transition-all ${
                  scopeType === 'enterprise'
                    ? 'border-amber-400 bg-amber-50/50'
                    : 'border-warm-200 bg-white hover:border-amber-400 hover:bg-amber-50/30'
                }`}
              >
                <Building2 size={16} className="text-warm-400 mt-0.5" />
                <div>
                  <div className="text-sm font-medium text-warm-800">指定企业</div>
                  <p className="text-xs text-warm-500 mt-0.5">单户体检（主路径）</p>
                </div>
              </button>
            </div>

            {scopeType === 'industry' && (
              <div>
                <label className="text-xs text-warm-500">选择行业</label>
                <select
                  value={industryL1 ?? ''}
                  onChange={(e) => setIndustryL1(e.target.value || null)}
                  className="mt-1 w-full h-9 rounded-lg border border-warm-200 bg-warm-50 px-2 text-sm text-warm-800 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber"
                >
                  <option value="">请选择行业…</option>
                  {industries.map((it) => (
                    <option key={it.industry_l1} value={it.industry_l1}>
                      {it.industry_l1}（{it.n} 家）
                    </option>
                  ))}
                </select>
              </div>
            )}

            {scopeType === 'enterprise' && (
              <div>
                <label className="text-xs text-warm-500">搜索并选择企业</label>
                <div className="mt-1 relative">
                  <Search size={14} className="absolute left-2 top-2.5 text-warm-400" />
                  <input
                    value={enterpriseQuery}
                    onChange={(e) => setEnterpriseQuery(e.target.value)}
                    placeholder="按「企业N」或行业/地区搜索…"
                    className="w-full h-9 pl-7 pr-2 rounded-lg border border-warm-200 bg-warm-50 text-sm text-warm-800 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber"
                  />
                </div>
                <select
                  value={enterpriseId ?? ''}
                  onChange={(e) => setEnterpriseId(e.target.value || null)}
                  className="mt-2 w-full h-9 rounded-lg border border-warm-200 bg-warm-50 px-2 text-sm text-warm-800 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber"
                >
                  <option value="">请选择企业…</option>
                  {enterprises.map((e) => (
                    <option key={e.enterprise_id} value={e.enterprise_id}>
                      {e.display_name}（{e.industry_l1} · {e.province}）
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        {/* S2 场景：快捷主题（非对话定制） */}
        {step === 1 && (
          <div className="space-y-2 max-h-[52vh] overflow-auto">
            {scopeType === 'enterprise' ? (
              <div className="rounded-xl border border-amber-400 bg-amber-50/50 p-3">
                <div className="text-sm font-medium text-warm-800">{ENTERPRISE_SCENARIO.title}</div>
                <p className="mt-0.5 text-xs text-warm-500">{ENTERPRISE_SCENARIO.subtitle}</p>
                <p className="mt-1 text-[11px] text-warm-600">
                  六维（税务/真实性/发票/行业/法律/财务）仍完整保留；此处是快捷体检模板，不是砍维度。
                </p>
              </div>
            ) : (
              <>
                <p className="text-[11px] text-warm-500 px-0.5">
                  快捷模板：放贷 / 评级 / 预警 / 稽查。若要自由组合章节，请关闭向导走「AI 对话定制」。
                </p>
                {REPORT_SCENARIOS.map((s) => {
                  const active = scenarioKey === s.key;
                  return (
                    <button
                      key={s.key}
                      onClick={() => setScenarioKey(s.key)}
                      className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-all ${
                        active
                          ? 'border-amber-400 bg-amber-50/50'
                          : 'border-warm-200 bg-white hover:border-amber-400 hover:bg-amber-50/30'
                      }`}
                    >
                      <div
                        className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg"
                        style={{ backgroundColor: `${s.accent}1a` }}
                      >
                        <Motif motif={s.motif} accent={s.accent} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-medium text-warm-800">{s.title}</div>
                        <p className="mt-0.5 text-xs text-warm-500">{s.subtitle}</p>
                        <p className="mt-1 text-[11px] text-warm-500">{s.description}</p>
                      </div>
                    </button>
                  );
                })}
              </>
            )}
          </div>
        )}
        {/* S3 确认 */}
        {step === 2 && scenario && (
          <div className="space-y-3">
            <div className="rounded-xl border border-warm-200 bg-warm-50 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Motif motif={scenario.motif} accent={scenario.accent} />
                <span className="font-semibold text-warm-800">{scenario.title}</span>
              </div>
              <p className="text-xs text-warm-500">{scenario.subtitle}</p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px]">
                <span className="rounded bg-amber/10 px-1.5 py-0.5 text-amber-700">范围：{scopeText}</span>
                {scenario.dataFocus.map((d) => (
                  <span key={d} className="rounded bg-warm-100 px-1.5 py-0.5 text-warm-600">
                    {d}
                  </span>
                ))}
              </div>
            </div>
            <p className="text-[11px] text-warm-400">
              确认后按「{scopeText}」×「{scenario.title}」生成<strong className="font-medium text-warm-600">快捷模板</strong>报告。
              自由拼章请关闭本向导，改用「AI 定制报告」。
            </p>
            {precheck.loading && (
              <p className="flex items-center gap-1.5 text-[11px] text-warm-500">
                <Loader2 className="w-3 h-3 animate-spin" />
                正在校验样本与章节可用性…
              </p>
            )}
            {!precheck.loading && precheck.ok === true && (
              <p className="text-[11px] text-warm-700">
                预校验通过
                {typeof precheck.sampleCount === 'number'
                  ? `（样本 ${precheck.sampleCount} 家）`
                  : ''}
                ，可生成。
              </p>
            )}
            {!precheck.loading && precheck.ok === false && (
              <div className="flex items-start gap-2 rounded-lg border border-terracotta/30 bg-terracotta/5 px-3 py-2">
                <AlertTriangle className="w-3.5 h-3.5 text-terracotta mt-0.5 flex-shrink-0" />
                <p className="text-[11px] text-terracotta">{precheck.reason || '当前范围暂不可生成报告。'}</p>
              </div>
            )}
          </div>
        )}

        {error && <p className="mt-3 text-xs text-terracotta">{error}</p>}

        {/* 底部操作 */}
        <div className="mt-5 flex items-center justify-between">
          <button
            onClick={step === 0 ? close : () => setStep((s) => s - 1)}
            disabled={busy}
            className="flex items-center gap-1 h-8 px-3 rounded-lg border border-warm-200 text-xs text-warm-600 hover:bg-warm-100 transition-colors disabled:opacity-50"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            {step === 0 ? '取消' : '上一步'}
          </button>

          {step < 2 ? (
            <button
              onClick={() => setStep((s) => s + 1)}
              disabled={!canNext || busy}
              className="flex items-center gap-1 h-8 px-4 rounded-lg bg-amber text-white text-xs hover:bg-amber-dark transition-colors disabled:opacity-50"
            >
              下一步
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              onClick={confirm}
              disabled={busy || precheck.loading || precheck.ok === false}
              className="flex items-center gap-1.5 h-8 px-4 rounded-lg bg-amber text-white text-xs hover:bg-amber-dark transition-colors disabled:opacity-50"
            >
              {busy || precheck.loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              生成报告
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
