import Card from '@/components/ui/Card';
import EvidenceChain from './EvidenceChain';
import BarChart from '@/components/charts/BarChart';
import LineChart from '@/components/charts/LineChart';
import PieChart from '@/components/charts/PieChart';
import type { ReportChapter as ChapterType } from '@/types/report';

interface ReportChapterProps {
  chapter: ChapterType;
  index: number;
}

function ChapterChart({ chart }: { chart: ChapterType['chart'] }) {
  if (!chart) return null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = chart.data as any;
  switch (chart.type) {
    case 'bar':
      return <BarChart data={data} />;
    case 'line':
      return <LineChart data={data} />;
    case 'pie':
      return <PieChart data={data} />;
    default:
      return null;
  }
}

export default function ReportChapter({ chapter, index }: ReportChapterProps) {
  return (
    <Card index={index} className="p-6">
      {/* 章节标题 */}
      <div className="flex items-center gap-3 mb-4">
        <div className="w-8 h-8 rounded-lg bg-amber/10 flex items-center justify-center text-amber text-sm font-semibold">
          {index + 1}
        </div>
        <div>
          <h3 className="text-base font-semibold text-warm-800">{chapter.title}</h3>
          <p className="text-xs text-warm-400">{chapter.description}</p>
        </div>
      </div>

      {/* 结论 */}
      <div className="mb-4">
        <h4 className="text-xs font-medium text-warm-500 uppercase tracking-wider mb-2">
          评估结论
        </h4>
        <p className="text-sm text-warm-700 leading-relaxed">{chapter.conclusion}</p>
      </div>

      {/* 图表 */}
      {chapter.chart && (
        <div className="mb-4">
          <ChapterChart chart={chapter.chart} />
        </div>
      )}

      {/* 证据链 */}
      {chapter.evidence_chain.length > 0 && (
        <EvidenceChain items={chapter.evidence_chain} />
      )}
    </Card>
  );
}
