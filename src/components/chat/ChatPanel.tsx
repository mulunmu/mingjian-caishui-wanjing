import { useEffect, useRef, useState } from 'react';
import { ChevronDown, History, RotateCcw, Trash2 } from 'lucide-react';
import useChatStore from '@/stores/chatStore';
import MessageList from './MessageList';
import ChatInput from './ChatInput';

interface ChatPanelProps {
  inputValue?: string;
  onInputChange?: (value: string) => void;
  onSend?: (text: string) => void;
  isLoading?: boolean;
}

function formatSessionTime(iso: string | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${mm}-${dd} ${hh}:${mi}`;
}

export default function ChatPanel({
  inputValue,
  onInputChange,
  onSend: externalOnSend,
  isLoading: externalLoading,
}: ChatPanelProps) {
  const {
    messages,
    isLoading: storeLoading,
    sendMessage,
    clickFollowUp,
    clearChat,
    sessions,
    sessionsLoading,
    sessionId,
    restoreHistory,
    loadSession,
    deleteSession,
    refreshSessions,
  } = useChatStore();

  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const restoredRef = useRef(false);

  const isLoading = externalLoading !== undefined ? externalLoading : storeLoading;
  const handleSend = externalOnSend || sendMessage;

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    void restoreHistory();
  }, [restoreHistory]);

  useEffect(() => {
    if (!open) return;
    void refreshSessions();
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open, refreshSessions]);

  return (
    <div className="flex flex-col h-full bg-warm-50">
      {/* 会话工具栏：历史恢复 + 清空当前（不清服务端归档） */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-warm-100 bg-white/60 flex-shrink-0">
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1 text-[11px] text-warm-500 hover:text-warm-700 px-2 py-1 rounded hover:bg-warm-100 transition-colors"
            title="历史会话"
          >
            <History size={12} />
            历史会话
            <ChevronDown size={11} className={open ? 'rotate-180 transition-transform' : 'transition-transform'} />
          </button>
          {open && (
            <div className="absolute left-0 top-full mt-1 z-20 w-72 max-h-64 overflow-y-auto rounded-lg border border-warm-200 bg-white shadow-md">
              {sessionsLoading && sessions.length === 0 ? (
                <p className="px-3 py-2 text-[11px] text-warm-400">加载中…</p>
              ) : sessions.length === 0 ? (
                <p className="px-3 py-2 text-[11px] text-warm-400">暂无历史会话</p>
              ) : (
                sessions.map((s) => {
                  const active = s.session_id === sessionId;
                  return (
                    <div
                      key={s.session_id}
                      className={`flex items-start gap-1 px-2 py-1.5 border-b border-warm-50 last:border-0 ${
                        active ? 'bg-amber/5' : 'hover:bg-warm-50'
                      }`}
                    >
                      <button
                        type="button"
                        className="flex-1 min-w-0 text-left"
                        onClick={() => {
                          void loadSession(s.session_id);
                          setOpen(false);
                        }}
                      >
                        <div className="text-[11px] text-warm-800 truncate">{s.summary || '（空会话）'}</div>
                        <div className="text-[10px] text-warm-400 mt-0.5">
                          {formatSessionTime(s.updated_at)}
                          {typeof s.message_count === 'number' ? ` · ${s.message_count} 条` : ''}
                          {active ? ' · 当前' : ''}
                        </div>
                      </button>
                      <button
                        type="button"
                        className="p-1 text-warm-300 hover:text-red-500 flex-shrink-0"
                        title="删除历史"
                        onClick={(e) => {
                          e.stopPropagation();
                          void deleteSession(s.session_id);
                        }}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={clearChat}
          className="flex items-center gap-1 text-[11px] text-warm-500 hover:text-warm-700 px-2 py-1 rounded hover:bg-warm-100 transition-colors"
          title="清空当前对话并开新会话（不删除历史归档）"
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
