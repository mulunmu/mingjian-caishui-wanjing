import { motion } from 'framer-motion';

interface EvidenceChainProps {
  items: string[];
  trace?: string;
}

export default function EvidenceChain({ items, trace }: EvidenceChainProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-warm-500 uppercase tracking-wider">
        证据链
      </h4>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <motion.li
            key={i}
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08, duration: 0.25 }}
            className="flex items-start gap-2 text-sm text-warm-600"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber mt-1.5 flex-shrink-0" />
            <span>{item}</span>
          </motion.li>
        ))}
      </ul>
      {trace && (
        <p className="text-xs text-mist mt-2 pl-3.5">数据来源：{trace}</p>
      )}
    </div>
  );
}
