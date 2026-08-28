import { motion } from 'framer-motion';
import type { DimensionItem, DimensionType } from '@/types/chat';

interface DimensionCardProps {
  item: DimensionItem;
  selected: boolean;
  onClick: () => void;
  index: number;
  icon?: React.ReactNode;
}

export default function DimensionCard({
  item,
  selected,
  onClick,
  index,
  icon,
}: DimensionCardProps) {
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
      whileHover={{ y: -2, boxShadow: '0 4px 16px rgba(44, 36, 24, 0.08)' }}
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className={`
        flex items-center gap-2 px-3 py-2 rounded-lg border text-sm
        transition-colors duration-200 cursor-pointer select-none
        ${selected
          ? 'border-amber bg-amber/5 text-amber shadow-warm-accent'
          : 'border-warm-200 bg-white text-warm-600 hover:border-warm-300'
        }
      `}
    >
      <span className={`w-5 h-5 flex items-center justify-center ${selected ? 'text-amber' : 'text-warm-400'}`}>
        {icon}
      </span>
      <span className="font-medium">{item.label}</span>
    </motion.button>
  );
}
