import { motion } from 'framer-motion';

interface UserMessageProps {
  content: string;
}

export default function UserMessage({ content }: UserMessageProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      className="flex justify-end"
    >
      <div className="max-w-[75%] px-4 py-2.5 rounded-xl rounded-br-sm bg-warm-100 text-warm-800 text-sm leading-relaxed">
        {content}
      </div>
    </motion.div>
  );
}
