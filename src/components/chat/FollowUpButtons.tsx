import { motion } from 'framer-motion';

interface FollowUpButtonsProps {
  questions: string[];
  onClick: (q: string) => void;
}

export default function FollowUpButtons({ questions, onClick }: FollowUpButtonsProps) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {questions.map((q, i) => (
        <motion.button
          key={q}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 + i * 0.1, duration: 0.25 }}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => onClick(q)}
          className="px-3 py-1.5 text-sm text-amber border border-amber/20 rounded-full
            hover:bg-amber/5 hover:border-amber/30
            transition-colors duration-150 cursor-pointer select-none"
        >
          → {q}
        </motion.button>
      ))}
    </div>
  );
}
