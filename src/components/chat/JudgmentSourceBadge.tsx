/** 研判/表述来源徽章：明确区分规则引擎 vs LLM */
export type JudgmentMode = 'rule' | 'llm' | 'template' | string;

const LABELS: Record<string, { text: string; className: string }> = {
  rule: { text: '规则引擎', className: 'bg-warm-100 text-warm-600 border-warm-200' },
  template: { text: '规则模板', className: 'bg-warm-100 text-warm-600 border-warm-200' },
  llm: { text: 'LLM', className: 'bg-sage/15 text-sage border-sage/30' },
};

interface JudgmentSourceBadgeProps {
  /** 数字与风险结论来源（当前恒为规则） */
  analysisMode?: JudgmentMode;
  /** 自然语言表述来源 */
  replySource?: JudgmentMode;
  /** 意图/语义解析来源 */
  parseSource?: JudgmentMode;
  className?: string;
}

function Chip({ mode, prefix }: { mode?: JudgmentMode; prefix: string }) {
  if (!mode) return null;
  const meta = LABELS[mode] || { text: String(mode), className: 'bg-warm-100 text-warm-500 border-warm-200' };
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-medium tracking-wide ${meta.className}`}
      title={`${prefix}：${meta.text}`}
    >
      <span className="opacity-70">{prefix}</span>
      {meta.text}
    </span>
  );
}

export default function JudgmentSourceBadge({
  analysisMode = 'rule',
  replySource,
  parseSource,
  className = '',
}: JudgmentSourceBadgeProps) {
  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      <Chip mode={analysisMode} prefix="分析" />
      <Chip mode={replySource === 'template' ? 'template' : replySource} prefix="表述" />
      {parseSource && parseSource !== 'rule' && <Chip mode={parseSource} prefix="解析" />}
    </div>
  );
}
