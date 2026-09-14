import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { FileText } from 'lucide-react';
import type { FollowUpItem, Message } from '@/types/chat';
import ConclusionCard from './ConclusionCard';
import EvidenceDrawer from './EvidenceDrawer';

interface AIMessageProps {
  message: Message;
  onFollowUp: (q: string | FollowUpItem) => void;
  onAction?: (target: string) => void;
}

export default function AIMessage({ message, onFollowUp, onAction }: AIMessageProps) {
  const hasEvidence = message.evidence && message.evidence.length > 0;
  const report = message.report;
  const hasCard =
    message.chart ||
    (message.followupItems && message.followupItems.length > 0) ||
    (message.followups && message.followups.length > 0) ||
    (message.actions && message.actions.length > 0) ||
    (message.guidanceCards && message.guidanceCards.length > 0);

  const reportCard = report ? (
    <Link
      to={`/report/${report.report_id}`}
      className="mt-2 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-warm-700 hover:bg-amber-100 transition-colors"
    >
      <FileText className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />
      <span className="truncate">已生成《{report.title || '风控报告'}》——点击查看 / 下载 / 发送</span>
    </Link>
  ) : null;

  if (hasCard) {
    return (
      <div className="flex justify-start max-w-[85%]">
        <div>
          <ConclusionCard
            conclusion={message.content}
            chart={message.chart}
            followups={message.followups || []}
            followupItems={message.followupItems}
            actions={message.actions}
            guidanceCards={message.guidanceCards}
            onFollowUp={onFollowUp}
            onAction={onAction}
          />
          {reportCard}
          {hasEvidence && <EvidenceDrawer evidence={message.evidence!} />}
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      className="flex justify-start max-w-[85%]"
    >
      <div className="flex">
        <div className="w-[3px] bg-amber rounded-full flex-shrink-0" />
        <div className="ml-3">
          <div className="px-4 py-2.5 rounded-xl rounded-bl-sm bg-white border border-warm-200 text-warm-800 text-sm leading-relaxed shadow-warm-sm">
            {message.content}
          </div>
          {reportCard}
          {hasEvidence && <EvidenceDrawer evidence={message.evidence!} />}
        </div>
      </div>
    </motion.div>
  );
}
