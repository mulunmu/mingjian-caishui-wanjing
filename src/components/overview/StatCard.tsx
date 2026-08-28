import { motion } from 'framer-motion';
import AnimatedNumber from '@/components/ui/AnimatedNumber';

interface StatCardProps {
  label: string;
  value: number;
  decimals?: number;
  suffix?: string;
  index?: number;
}

export default function StatCard({
  label,
  value,
  decimals = 0,
  suffix = '',
  index = 0,
}: StatCardProps) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 12 },
        visible: (i: number) => ({
          opacity: 1,
          y: 0,
          transition: { delay: i * 0.08, duration: 0.3 },
        }),
      }}
      initial="hidden"
      animate="visible"
      custom={index}
      className="bg-white rounded-lg border border-warm-200 p-5 shadow-warm-sm
        border-b-[3px] border-b-amber"
    >
      <div className="text-2xl font-bold text-warm-800 font-number">
        <AnimatedNumber value={value} decimals={decimals} suffix={suffix} />
      </div>
      <p className="text-xs text-warm-400 mt-1">{label}</p>
    </motion.div>
  );
}
