import { motion } from 'framer-motion';
import type { FollowUpItem } from '@/types/chat';

interface FollowUpButtonsProps {
  questions?: string[];
  items?: FollowUpItem[];
  onClick: (q: string | FollowUpItem) => void;
}

function tone(type: string | undefined): string {
  if (type === 'action') {
    return 'text-terracotta border-terracotta/25 hover:bg-terracotta/5 hover:border-terracotta/40';
  }
  if (type === 'navigate') {
    return 'text-warm-700 border-warm-300 hover:bg-warm-100 hover:border-warm-400';
  }
  if (type === 'drilldown') {
    return 'text-amber border-amber/30 hover:bg-amber/5 hover:border-amber/50';
  }
  return 'text-amber border-amber/20 hover:bg-amber/5 hover:border-amber/30';
}

function prefix(type: string | undefined): string {
  if (type === 'action') return '做 · ';
  if (type === 'navigate') return '去 · ';
  if (type === 'drilldown') return '看 · ';
  return '→ ';
}

export default function FollowUpButtons({ questions, items, onClick }: FollowUpButtonsProps) {
  const list: FollowUpItem[] =
    items && items.length > 0
      ? items
      : (questions || []).map((label) => ({ type: 'query', label }));

  if (list.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {list.map((item, i) => (
        <motion.button
          key={`${item.type}-${item.label}-${item.op || item.target || i}`}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 + i * 0.1, duration: 0.25 }}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => onClick(item)}
          className={`px-3 py-1.5 text-sm border rounded-full
            transition-colors duration-150 cursor-pointer select-none ${tone(item.type)}`}
        >
          {prefix(item.type)}
          {item.label}
        </motion.button>
      ))}
    </div>
  );
}
