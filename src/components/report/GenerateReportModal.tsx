import { Crown, FileText, Loader2, X } from 'lucide-react';
import { REPORT_SCENARIOS, type ReportScenarioDef } from '@/constants/reportScenarios';

interface GenerateReportModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (scenario: ReportScenarioDef) => void;
  busyScenario: string | null;
  error: string | null;
}

/** 报告生成模块选择弹窗：选择场景切片生成（付费模块触发升级提示）。 */
export default function GenerateReportModal({
  open,
  onClose,
  onSelect,
  busyScenario,
  error,
}: GenerateReportModalProps) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-warm-900/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-[560px] max-w-[94vw] rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded text-warm-400 hover:bg-warm-100 transition-colors"
          title="关闭"
        >
          <X size={16} />
        </button>

        <h3 className="mb-1 text-base font-semibold text-warm-800">生成风控报告</h3>
        <p className="mb-4 text-xs text-warm-400">选择报告模块，系统按当前样本数据即时生成切片报告。</p>

        <div className="space-y-2">
          {REPORT_SCENARIOS.map((s) => {
            const busy = busyScenario === s.key;
            const isPremium = s.tier === 'premium';
            return (
              <button
                key={s.key}
                onClick={() => onSelect(s)}
                disabled={busyScenario !== null}
                className="group flex w-full items-start gap-3 rounded-xl border border-warm-200 bg-white p-3 text-left transition-all hover:border-amber-400 hover:bg-amber-50/40 disabled:opacity-60"
              >
                <div
                  className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg ${
                    isPremium ? 'bg-amber-100' : 'bg-warm-100'
                  }`}
                >
                  {busy ? (
                    <Loader2 className="h-4 w-4 animate-spin text-warm-500" />
                  ) : isPremium ? (
                    <Crown className="h-4 w-4 text-amber-500" />
                  ) : (
                    <FileText className="h-4 w-4 text-warm-500 group-hover:text-amber-600" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-warm-800">{s.label}</span>
                    {isPremium && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">
                        付费
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-warm-500">{s.description}</p>
                  <p className="mt-1 text-[11px] text-warm-400">
                    章节：{s.chapters.join(' · ')}
                  </p>
                </div>
              </button>
            );
          })}
        </div>

        {error && <p className="mt-3 text-xs text-terracotta">{error}</p>}
      </div>
    </div>
  );
}
