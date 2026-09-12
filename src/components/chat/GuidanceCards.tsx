import { motion } from 'framer-motion';
import type { GuidanceCard } from '@/types/chat';

/** ① ② ③ ④ 序号 */
const CIRCLED = ['①', '②', '③', '④', '⑤', '⑥'];

interface GuidanceCardsProps {
  cards: GuidanceCard[];
  onClick: (label: string) => void;
}

/**
 * 强拦截引导卡片（方案 A）：当定制报告无可用数据时，用可点击的调整卡片替代
 * 「确认生成」按钮，让用户一步到位改范围/换章节，而不是空跑失败后被文案堵住。
 */
export default function GuidanceCards({ cards, onClick }: GuidanceCardsProps) {
  if (cards.length === 0) return null;
  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs text-warm-500">当前范围暂无可用数据，请选择一种调整方式：</p>
      {cards.map((c, i) => (
        <motion.button
          key={c.label}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 + i * 0.08, duration: 0.25 }}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          onClick={() => onClick(c.label)}
          className="w-full flex items-start gap-3 p-3 rounded-lg border border-amber/20 bg-amber/5 text-left
            hover:bg-amber/10 hover:border-amber/40
            transition-colors duration-150 cursor-pointer select-none"
        >
          <span className="text-amber text-base leading-none mt-0.5 flex-shrink-0">
            {CIRCLED[i] || `${i + 1}.`}
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-medium text-warm-800">{c.label}</span>
            <span className="block text-xs text-warm-500 mt-0.5 leading-relaxed">
              {c.description}
            </span>
          </span>
        </motion.button>
      ))}
    </div>
  );
}
