import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import type { FollowUpItem, Message } from '@/types/chat';
import AIMessage from './AIMessage';
import UserMessage from './UserMessage';
import TypingIndicator from './TypingIndicator';
import useChatStore from '@/stores/chatStore';

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  onFollowUp: (q: string | FollowUpItem) => void;
}

function resolveNavigateTarget(target: string | undefined): string | 'ingest_modal' | null {
  if (!target) return null;
  if (target === 'ingest' || target === '/ingest') return 'ingest_modal';
  if (target === 'report_generate' || target === 'report' || target === '/report') {
    return '/report?wizard=1';
  }
  if (target === 'overview' || target === '/overview') return '/overview';
  if (target.startsWith('/')) return target;
  return null;
}

export default function MessageList({ messages, isLoading, onFollowUp }: MessageListProps) {
  const navigate = useNavigate();
  const openIngestModal = useChatStore((s) => s.openIngestModal);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleFollowUp = (q: string | FollowUpItem) => {
    if (typeof q === 'string') {
      if (q === '查看整体概览' || q === '查看风险预警') {
        navigate('/overview');
        return;
      }
      if (q.includes('数据接入') || q.includes('数据怎么导入')) {
        openIngestModal();
        return;
      }
      if (q.includes('生成报告') || q.includes('报告生成')) {
        navigate('/report?wizard=1');
        return;
      }
      onFollowUp(q);
      return;
    }

    if (q.type === 'navigate') {
      const path = resolveNavigateTarget(q.target);
      if (path === 'ingest_modal') {
        openIngestModal();
        return;
      }
      if (path) {
        navigate(path);
        return;
      }
    }

    if (q.type === 'action') {
      // 动作不进对话复读：仍走后端 action 分支拿人工核查提示
      onFollowUp(q);
      return;
    }

    onFollowUp(q);
  };

  const handleAction = (target: string) => {
    const path = resolveNavigateTarget(target) || target;
    if (path === 'ingest_modal') {
      openIngestModal();
      return;
    }
    navigate(path);
  };

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg) =>
        msg.role === 'user' ? (
          <UserMessage key={msg.id} content={msg.content} />
        ) : (
          <AIMessage key={msg.id} message={msg} onFollowUp={handleFollowUp} onAction={handleAction} />
        )
      )}
      {isLoading && <TypingIndicator />}
      <div ref={bottomRef} />
    </div>
  );
}
