import { RotateCcw } from 'lucide-react';
import useChatStore from '@/stores/chatStore';
import MessageList from './MessageList';
import ChatInput from './ChatInput';

interface ChatPanelProps {
  inputValue?: string;
  onInputChange?: (value: string) => void;
  onSend?: (text: string) => void;
  isLoading?: boolean;
}

export default function ChatPanel({
  inputValue,
  onInputChange,
  onSend: externalOnSend,
  isLoading: externalLoading,
}: ChatPanelProps) {
  const { messages, isLoading: storeLoading, sendMessage, clickFollowUp, clearChat } =
    useChatStore();

  const isLoading = externalLoading !== undefined ? externalLoading : storeLoading;
  const handleSend = externalOnSend || sendMessage;

  return (
    <div className="flex flex-col h-full bg-warm-50">
      {/* 会话工具栏：主动清空对话，避免跨主体记忆串味 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-warm-100 bg-white/60 flex-shrink-0">
        <span className="text-[11px] text-warm-400">当前会话</span>
        <button
          type="button"
          onClick={clearChat}
          className="flex items-center gap-1 text-[11px] text-warm-500 hover:text-warm-700 px-2 py-1 rounded hover:bg-warm-100 transition-colors"
          title="清空当前对话与上下文记忆"
        >
          <RotateCcw size={12} />
          清空对话
        </button>
      </div>
      <MessageList
        messages={messages}
        isLoading={isLoading}
        onFollowUp={clickFollowUp}
      />
      <ChatInput
        onSend={handleSend}
        disabled={isLoading}
        value={inputValue}
        onChange={onInputChange}
      />
    </div>
  );
}
