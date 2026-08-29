import { useState, useEffect } from 'react';
import { ArrowLeft, ArrowRight, Loader2, Sparkles, X, Building2 } from 'lucide-react';
import {
  REPORT_SCENARIOS,
  type ReportScenarioDef,
  type ScenarioMotif,
} from '@/constants/reportScenarios';
import { riskApi, type IndustryItem } from '@/api/risk';

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

/** 向导偏好：范围（行业）+ 场景；真正传给后端（非占位）。 */
export interface WizardPrefs {
  scenarioKey: string;
  industry_l1?: string | null;
}

interface ReportWizardProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (scenario: ReportScenarioDef, prefs: WizardPrefs) => void;
  busy: boolean;
  error: string | null;
}

const STEP_TITLES = ['选择范围', '选择场景', '确认生成'];

export default function ReportWizard({ open, onClose, onConfirm, busy, error }: ReportWizardProps) {
  const [step, setStep] = useState(0);
  const [scopeType, setScopeType] = useState<'all' | 'industry'>('all');
  const [industryL1, setIndustryL1] = useState<string | null>(null);
  const [industries, setIndustries] = useState<IndustryItem[]>([]);
  const [scenarioKey, setScenarioKey] = useState<string | null>(null);

  // 打开时拉取行业列表（供范围下拉）；失败不阻断（下拉为空，仍可选「全部样本」）
  useEffect(() => {
    if (!open) return;
    riskApi
      .getIndustries()
      .then(setIndustries)
      .catch(() => setIndustries([]));
  }, [open]);

  if (!open) return null;

  const scenario = REPORT_SCENARIOS.find((s) => s.key === scenarioKey) || null;

  const reset = () => {
    setStep(0);
    setScopeType('all');
    setIndustryL1(null);
    setScenarioKey(null);
  };

  const close = () => {
    reset();
    onClose();
  };

  const canNext =
    step === 0
      ? scopeType === 'all' || !!industryL1
      : step === 1
        ? !!scenarioKey
        : true;

  const confirm = () => {
    if (!scenario) return;
    onConfirm(scenario, {
      scenarioKey: scenario.key,
      industry_l1: scopeType === 'industry' ? industryL1 : null,
    });
  };

  const scopeText =
    scopeType === 'industry' && industryL1 ? industryL1 : '全部样本';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-warm-900/40 backdrop-blur-sm"
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
        <p className="mb-4 text-xs text-warm-400">
          先选范围，再选场景；数据侧重随场景确定，语气随场景口径（内部研判）。
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
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setScopeType('all')}
                className={`flex items-start gap-2 rounded-xl border p-3 text-left transition-all ${
                  scopeType === 'all'
                    ? 'border-amber-400 bg-amber-50/50'
                    : 'border-warm-200 bg-white hover:border-amber-400 hover:bg-amber-50/30'
                }`}
              >
                <Building2 size={16} className="text-warm-400 mt-0.5" />
                <div>
                  <div className="text-sm font-medium text-warm-800">全部样本</div>
                  <p className="text-xs text-warm-500 mt-0.5">覆盖已接入的全部匿名样本</p>
                </div>
              </button>
              <button
                onClick={() => setScopeType('industry')}
                className={`flex items-start gap-2 rounded-xl border p-3 text-left transition-all ${
                  scopeType === 'industry'
                    ? 'border-amber-400 bg-amber-50/50'
                    : 'border-warm-200 bg-white hover:border-amber-400 hover:bg-amber-50/30'
                }`}
              >
                <Building2 size={16} className="text-warm-400 mt-0.5" />
                <div>
                  <div className="text-sm font-medium text-warm-800">指定行业</div>
                  <p className="text-xs text-warm-500 mt-0.5">聚焦某个行业大类的切片</p>
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
          </div>
        )}

        {/* S2 场景 */}
        {step === 1 && (
          <div className="space-y-2 max-h-[52vh] overflow-auto">
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
                    <div className="mt-1 flex flex-wrap gap-1">
                      {s.dataFocus.map((d) => (
                        <span key={d} className="rounded bg-warm-100 px-1.5 py-0.5 text-[10px] text-warm-600">
                          {d}
                        </span>
                      ))}
                    </div>
                  </div>
                </button>
              );
            })}
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
              确认后按「{scopeText}」范围与「{scenario.title}」场景即时生成报告（通用模板）。
            </p>
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
              disabled={busy}
              className="flex items-center gap-1.5 h-8 px-4 rounded-lg bg-amber text-white text-xs hover:bg-amber-dark transition-colors disabled:opacity-50"
            >
              {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              生成报告
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
