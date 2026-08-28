import { motion } from 'framer-motion';
import type { FunctionItem, FunctionType } from '@/types/chat';

interface FunctionCardProps {
  item: FunctionItem;
  selected: boolean;
  onClick: () => void;
  index: number;
  icon?: React.ReactNode;
}

export default function FunctionCard({
  item,
  selected,
  onClick,
  index,
  icon,
}: FunctionCardProps) {
  return (
    <motion.button
      variants={{
        hidden: { opacity: 0, y: 12 },
        visible: (i: number) => ({
          opacity: 1,
          y: 0,
          transition: { delay: i * 0.06, duration: 0.3, ease: [0.4, 0, 0.2, 1] },
        }),
      }}
      initial="hidden"
      animate="visible"
      custom={index}
      whileHover={{ borderColor: '#C08B30' }}
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className={`
        flex items-start gap-2.5 px-3 py-2.5 rounded-lg border text-left
        transition-colors duration-200 cursor-pointer select-none
        ${selected
          ? 'border-amber bg-amber/5'
          : 'border-warm-200 bg-white hover:border-warm-300'
        }
      `}
    >
      {/* 左侧竖线 */}
      <div
        className={`
          w-[3px] rounded-full flex-shrink-0 mt-0.5
          transition-colors duration-200
          ${selected ? 'bg-amber h-8' : 'bg-warm-200 h-6'}
        `}
      />
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-1.5">
          <span className={`w-4 h-4 flex items-center justify-center ${selected ? 'text-amber' : 'text-warm-400'}`}>
            {icon}
          </span>
          <span
            className={`text-sm font-medium ${
              selected ? 'text-amber' : 'text-warm-700'
            }`}
          >
            {item.label}
          </span>
        </div>
        <span className="text-xs text-warm-400">{item.description}</span>
      </div>
    </motion.button>
  );
}
