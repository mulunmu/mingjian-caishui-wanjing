import { motion } from 'framer-motion';
import type { Message } from '@/types/chat';
import ConclusionCard from './ConclusionCard';
import EvidenceDrawer from './EvidenceDrawer';
import JudgmentSourceBadge from './JudgmentSourceBadge';

interface AIMessageProps {
  message: Message;
  onFollowUp: (q: string) => void;
  onAction?: (target: string) => void;
}

export default function AIMessage({ message, onFollowUp, onAction }: AIMessageProps) {
  const hasEvidence = message.evidence && message.evidence.length > 0;
  const showSource = Boolean(message.replySource || message.analysisMode || message.parseSource);
  const hasCard =
    message.chart ||
    (message.followups && message.followups.length > 0) ||
    (message.actions && message.actions.length > 0) ||
    (message.guidanceCards && message.guidanceCards.length > 0);

  // 如果有图表、追问或引导动作，使用 ConclusionCard 渲染
  if (hasCard) {
    return (
      <div className="flex justify-start max-w-[85%]">
        <div>
          <ConclusionCard
            conclusion={message.content}
            chart={message.chart}
            followups={message.followups || []}
            actions={message.actions}
            guidanceCards={message.guidanceCards}
            onFollowUp={onFollowUp}
            onAction={onAction}
            replySource={message.replySource}
            analysisMode={message.analysisMode || 'rule'}
            parseSource={message.parseSource}
          />
          {hasEvidence && <EvidenceDrawer evidence={message.evidence!} />}
        </div>
      </div>
    );
  }

  // 纯文本 AI 回复
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
          {showSource && (
            <JudgmentSourceBadge
              analysisMode={message.analysisMode || 'rule'}
              replySource={message.replySource}
              parseSource={message.parseSource}
              className="mb-1.5"
            />
          )}
          <div className="px-4 py-2.5 rounded-xl rounded-bl-sm bg-white border border-warm-200 text-warm-800 text-sm leading-relaxed shadow-warm-sm">
            {message.content}
          </div>
          {hasEvidence && <EvidenceDrawer evidence={message.evidence!} />}
        </div>
      </div>
    </motion.div>
  );
}
