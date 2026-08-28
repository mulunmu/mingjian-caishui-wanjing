import { motion } from 'framer-motion';
import Card from '@/components/ui/Card';

interface WarningSignal {
  id: string;
  label: string;
  count: number;
  level: 'high' | 'medium' | 'low';
  icon: string;
}

interface WarningPanelProps {
  signals: WarningSignal[];
}

const levelColors = {
  high: 'text-terracotta bg-terracotta/10',
  medium: 'text-amber bg-amber/10',
  low: 'text-sage bg-sage/10',
};

export default function WarningPanel({ signals }: WarningPanelProps) {
  return (
    <Card index={2} className="p-5">
      <h3 className="text-sm font-semibold text-warm-700 mb-3">预警信号</h3>
      <div className="space-y-2">
        {signals.map((signal, i) => (
          <motion.div
            key={signal.id}
            variants={{
              hidden: { opacity: 0, x: -4 },
              visible: (idx: number) => ({
                opacity: 1,
                x: 0,
                transition: { delay: idx * 0.06, duration: 0.25 },
              }),
            }}
            initial="hidden"
            animate="visible"
            custom={i}
            className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-warm-50 transition-colors"
          >
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm ${
                levelColors[signal.level]
              }`}
            >
              {signal.icon === 'alert' && '⚠️'}
              {signal.icon === 'clock' && '⏰'}
              {signal.icon === 'trending' && '📈'}
              {signal.icon === 'percent' && '%'}
              {signal.icon === 'shield' && '🛡️'}
            </div>
            <div className="flex-1">
              <span className="text-sm text-warm-700">{signal.label}</span>
            </div>
            <span className="text-sm font-semibold font-number text-warm-800">
              {signal.count}
            </span>
          </motion.div>
        ))}
      </div>
    </Card>
  );
}
