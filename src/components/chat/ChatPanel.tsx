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
  const { messages, isLoading: storeLoading, sendMessage, clickFollowUp } = useChatStore();

  const isLoading = externalLoading !== undefined ? externalLoading : storeLoading;
  const handleSend = externalOnSend || sendMessage;

  return (
    <div className="flex flex-col h-full bg-warm-50">
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
