import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Message } from '@/types/chat';
import AIMessage from './AIMessage';
import UserMessage from './UserMessage';
import TypingIndicator from './TypingIndicator';

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  onFollowUp: (q: string) => void;
}

export default function MessageList({ messages, isLoading, onFollowUp }: MessageListProps) {
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // 追问中「查看整体概览」是导航动作而非聊天问题 → 真跳转
  const handleFollowUp = (q: string) => {
    if (q === '查看整体概览') {
      navigate('/overview');
      return;
    }
    onFollowUp(q);
  };

  // 引导动作：跳转到具体功能页（报告向导 / 数据接入等）
  const handleAction = (target: string) => {
    navigate(target);
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
