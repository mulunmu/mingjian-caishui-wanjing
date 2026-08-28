import { useState, useRef, type KeyboardEvent } from 'react';
import { motion } from 'framer-motion';

interface ChatInputProps {
  onSend: (text: string) => void;
  disabled?: boolean;
  value?: string;
  onChange?: (value: string) => void;
}

export default function ChatInput({
  onSend,
  disabled = false,
  value: controlledValue,
  onChange,
}: ChatInputProps) {
  const [internalValue, setInternalValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const value = controlledValue !== undefined ? controlledValue : internalValue;
  const setValue = onChange || setInternalValue;

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInternalValue('');
    // 重置高度
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 自动调整高度
  const handleInput = (val: string) => {
    setValue(val);
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  };

  return (
    <div
      className="flex items-end gap-2 px-4 py-3 bg-white border-t border-warm-200"
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => handleInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="输入问题，或点击卡片快速选择…"
        rows={1}
        maxLength={2000}
        disabled={disabled}
        className="flex-1 resize-none px-3 py-2.5 text-sm bg-warm-50 border border-warm-200
          rounded-lg outline-none text-warm-800 placeholder:text-warm-400
          focus:border-amber focus:shadow-[0_0_0_3px_rgba(192,139,48,0.1)]
          transition-all duration-200
          disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ maxHeight: 120 }}
      />
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className="flex-shrink-0 w-10 h-10 flex items-center justify-center
          bg-amber text-white rounded-lg
          hover:bg-amber-dark active:bg-amber-dark/90
          disabled:opacity-40 disabled:cursor-not-allowed
          transition-colors duration-150"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 2L11 13" />
          <path d="M22 2L15 22L11 13L2 9L22 2Z" />
        </svg>
      </motion.button>
    </div>
  );
}
