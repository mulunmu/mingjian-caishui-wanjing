import { motion } from 'framer-motion';
import type { ComboItem } from '@/types/chat';

interface ComboCardProps {
  item: ComboItem;
  onClick: () => void;
  index: number;
  icon?: React.ReactNode;
}

export default function ComboCard({ item, onClick, index, icon }: ComboCardProps) {
  return (
    <motion.button
      variants={{
        hidden: { opacity: 0, scale: 0.95 },
        visible: (i: number) => ({
          opacity: 1,
          scale: 1,
          transition: { delay: i * 0.06, duration: 0.25 },
        }),
      }}
      initial="hidden"
      animate="visible"
      custom={index}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
        bg-amber/8 border border-amber/15 text-amber text-sm
        hover:bg-amber/12 hover:border-amber/25
        transition-colors duration-150 cursor-pointer select-none"
    >
      <span className="w-3.5 h-3.5 flex items-center justify-center opacity-70">
        {icon}
      </span>
      <span>{item.label}</span>
    </motion.button>
  );
}
