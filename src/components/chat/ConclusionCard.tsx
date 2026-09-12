import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import type { ChartConfig, ChatAction, GuidanceCard } from '@/types/chat';
import FollowUpButtons from './FollowUpButtons';
import GuidanceCards from './GuidanceCards';
import JudgmentSourceBadge from './JudgmentSourceBadge';
import BarChart from '@/components/charts/BarChart';
import LineChart from '@/components/charts/LineChart';
import PieChart from '@/components/charts/PieChart';
import RadarChart from '@/components/charts/RadarChart';
import Heatmap from '@/components/charts/Heatmap';
import ScatterChart from '@/components/charts/ScatterChart';

interface ConclusionCardProps {
  conclusion: string;
  chart?: ChartConfig;
  followups: string[];
  actions?: ChatAction[];
  guidanceCards?: GuidanceCard[];
  onFollowUp: (q: string) => void;
  onAction?: (target: string) => void;
  replySource?: string;
  analysisMode?: string;
  parseSource?: string;
}

function ChartRenderer({ chart }: { chart: ChartConfig }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = chart.data as any;
  switch (chart.type) {
    case 'bar':
      return <BarChart data={data} />;
    case 'line':
      return <LineChart data={data} />;
    case 'pie':
      return <PieChart data={data} />;
    case 'radar':
      return <RadarChart data={data} />;
    case 'heatmap':
      return <Heatmap data={data} />;
    case 'scatter':
      return <ScatterChart data={data} />;
    default:
      return null;
  }
}

export default function ConclusionCard({
  conclusion,
  chart,
  followups,
  actions,
  guidanceCards,
  onFollowUp,
  onAction,
  replySource,
  analysisMode = 'rule',
  parseSource,
}: ConclusionCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      className="bg-white rounded-lg border border-warm-200 shadow-warm-sm overflow-hidden"
    >
      <div className="flex">
        <div className="w-[3px] bg-amber flex-shrink-0" />
        <div className="flex-1 p-4">
          <JudgmentSourceBadge
            analysisMode={analysisMode}
            replySource={replySource}
            parseSource={parseSource}
            className="mb-2"
          />
          <p className="text-warm-800 text-sm leading-relaxed">{conclusion}</p>

          {chart && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.4 }}
              className="mt-3"
            >
              <ChartRenderer chart={chart} />
            </motion.div>
          )}

          {actions && actions.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3">
              {actions.map((a) => (
                <motion.button
                  key={`${a.label}-${a.target}`}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25 }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => onAction?.(a.target)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-amber hover:bg-amber-dark
                    rounded-full transition-colors duration-150 cursor-pointer select-none"
                >
                  {a.label}
                  <ArrowRight className="w-3.5 h-3.5" />
                </motion.button>
              ))}
            </div>
          )}

          {guidanceCards && guidanceCards.length > 0 ? (
            <GuidanceCards cards={guidanceCards} onClick={onFollowUp} />
          ) : (
            followups.length > 0 && (
              <FollowUpButtons questions={followups} onClick={onFollowUp} />
            )
          )}
        </div>
      </div>
    </motion.div>
  );
}
