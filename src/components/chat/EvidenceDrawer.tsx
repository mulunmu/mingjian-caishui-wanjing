import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileSearch, ChevronDown, ChevronUp, Database, Shield } from 'lucide-react';
import type { EvidenceItem } from '@/types/chat';

interface EvidenceDrawerProps {
  evidence: EvidenceItem[];
}

/** 置信度徽章 */
function ConfidenceBadge({ confidence }: { confidence?: string }) {
  if (!confidence) return null;
  const map: Record<string, { label: string; color: string }> = {
    computed: { label: '计算值', color: 'bg-emerald-100 text-emerald-700' },
    inferred: { label: '推断值', color: 'bg-amber-100 text-amber-700' },
    estimated: { label: '估算值', color: 'bg-slate-100 text-slate-600' },
  };
  const info = map[confidence] || { label: confidence, color: 'bg-slate-100 text-slate-600' };
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${info.color}`}>
      {info.label}
    </span>
  );
}

export default function EvidenceDrawer({ evidence }: EvidenceDrawerProps) {
  const [open, setOpen] = useState(false);

  if (!evidence || evidence.length === 0) return null;

  return (
    <div className="mt-2">
      {/* 触发按钮 */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
          bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100
          transition-colors duration-200 cursor-pointer"
      >
        <FileSearch size={14} />
        <span>查看溯源 ({evidence.length})</span>
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {/* 抽屉内容 */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-2 rounded-lg border border-warm-200 bg-warm-50/50 divide-y divide-warm-100">
              {evidence.map((item, idx) => (
                <div key={idx} className="px-3 py-2.5">
                  {/* 来源行 */}
                  <div className="flex items-center gap-2 mb-1">
                    <Database size={12} className="text-warm-400 flex-shrink-0" />
                    <span className="text-[11px] font-mono text-warm-500 truncate">
                      {item.source}
                    </span>
                    <ConfidenceBadge confidence={item.confidence} />
                  </div>
                  {/* 结论内容 */}
                  <p className="text-xs text-warm-700 leading-relaxed pl-5">
                    {item.content}
                  </p>
                  {/* 证据链 */}
                  {item.evidence_chain && item.evidence_chain.length > 0 && (
                    <div className="mt-1.5 pl-5 flex flex-wrap gap-1">
                      {item.evidence_chain.map((chain, ci) => (
                        <span
                          key={ci}
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-white border border-warm-200 text-[10px] text-warm-500"
                        >
                          <Shield size={9} />
                          {chain}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
