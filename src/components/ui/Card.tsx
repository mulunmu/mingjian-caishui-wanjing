import { type ReactNode } from 'react';
import { motion } from 'framer-motion';

interface CardProps {
  children: ReactNode;
  className?: string;
  selected?: boolean;
  hoverable?: boolean;
  onClick?: () => void;
  /** 入场动画索引（stagger 用） */
  index?: number;
}

export default function Card({
  children,
  className = '',
  selected = false,
  hoverable = false,
  onClick,
  index = 0,
}: CardProps) {
  return (
    <motion.div
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
      whileHover={hoverable ? { y: -2, boxShadow: '0 8px 32px rgba(44, 36, 24, 0.12)' } : undefined}
      onClick={onClick}
      className={`
        bg-white rounded-lg border transition-colors duration-200
        ${selected
          ? 'border-amber shadow-warm-accent'
          : 'border-warm-200 shadow-warm-sm'
        }
        ${hoverable ? 'cursor-pointer hover:border-amber-light' : ''}
        ${onClick ? 'cursor-pointer' : ''}
        ${className}
      `}
    >
      {children}
    </motion.div>
  );
}
