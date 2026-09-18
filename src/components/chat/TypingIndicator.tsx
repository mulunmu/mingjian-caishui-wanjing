import { motion } from 'framer-motion';
import { Check, LoaderCircle } from 'lucide-react';
import type { ProcessStep } from '@/types/chat';

export default function TypingIndicator({ steps = [] }: { steps?: ProcessStep[] }) {
  if (steps.length > 0) {
    return (
      <div className="ml-4 max-w-[80%] rounded-xl border border-warm-200 bg-white px-4 py-3 shadow-warm-sm">
        <div className="space-y-2">
          {steps.slice(-5).map((step, index, list) => {
            const active = index === list.length - 1;
            return (
              <div key={`${step.stage}-${index}`} className="flex items-start gap-2 text-xs">
                {active ? (
                  <LoaderCircle className="mt-0.5 h-3.5 w-3.5 animate-spin text-amber-600" />
                ) : (
                  <Check className="mt-0.5 h-3.5 w-3.5 text-emerald-600" />
                )}
                <div className="min-w-0">
                  <div className={active ? 'font-medium text-warm-800' : 'text-warm-500'}>
                    {step.label}
                  </div>
                  {step.detail && <div className="mt-0.5 text-warm-400">{step.detail}</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1 px-4 py-2">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full bg-warm-300"
          animate={{
            y: [0, -6, 0],
            opacity: [0.4, 1, 0.4],
          }}
          transition={{
            duration: 1.2,
            repeat: Infinity,
            delay: i * 0.15,
            ease: 'easeInOut',
          }}
        />
      ))}
    </div>
  );
}
