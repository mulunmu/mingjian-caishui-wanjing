import { ChevronDown, ListChecks } from 'lucide-react';
import type { ProcessStep } from '@/types/chat';

export default function ProcessTimeline({
  steps,
  planSummary,
  plannerStatus,
  toolIds = [],
}: {
  steps: ProcessStep[];
  planSummary?: string;
  plannerStatus?: string;
  toolIds?: string[];
}) {
  return (
    <details className="mt-2 rounded-lg border border-warm-200 bg-warm-50/60 px-3 py-2 text-xs text-warm-600">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-warm-700">
        <ListChecks className="h-3.5 w-3.5 text-amber-600" />
        <span>分析过程</span>
        <ChevronDown className="ml-auto h-3.5 w-3.5" />
      </summary>
      <div className="mt-2 space-y-1.5 border-t border-warm-200 pt-2">
        {planSummary && (
          <div className="rounded-md bg-white/80 px-2 py-1.5 text-warm-700">
            <div>{planSummary}</div>
            <div className="mt-0.5 text-[10px] text-warm-400">
              {plannerStatus ? `规划状态：${plannerStatus}` : '规划状态：执行中'}
              {toolIds.length > 0 ? ` · ${toolIds.length} 个模块` : ''}
            </div>
          </div>
        )}
        {steps.map((step, index) => (
          <div key={`${step.stage}-${index}`} className="flex gap-2">
            <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
            <div>
              <div>{step.label}</div>
              {step.detail && <div className="text-warm-400">{step.detail}</div>}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}
