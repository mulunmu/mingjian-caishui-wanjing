import type { Report } from '@/types/report';
import ReportChapter from './ReportChapter';
import ReportActions from './ReportActions';
import Divider from '@/components/ui/Divider';
import { formatDate } from '@/utils/formatters';

interface ReportPreviewProps {
  report: Report;
  onDownload: (id: string) => void;
  onSendEmail: (id: string, email: string) => void;
}

export default function ReportPreview({
  report,
  onDownload,
  onSendEmail,
}: ReportPreviewProps) {
  return (
    <div className="max-w-3xl mx-auto py-8 px-4 space-y-6">
      {/* 报告头部 */}
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-warm-800">{report.title}</h1>
        <p className="text-sm text-warm-500">{report.subtitle}</p>
        <p className="text-xs text-warm-400">
          生成于 {formatDate(report.generated_at)} · 维度：{report.dimension}
        </p>
      </div>

      <Divider />

      {/* 操作栏 */}
      <ReportActions
        reportId={report.id}
        onDownload={onDownload}
        onSendEmail={onSendEmail}
      />

      <Divider />

      {/* 摘要 */}
      <div className="bg-amber/5 border border-amber/15 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-amber mb-2">摘要</h2>
        <p className="text-sm text-warm-700 leading-relaxed">{report.summary}</p>
      </div>

      {/* 章节 */}
      <div className="space-y-4">
        {report.chapters.map((chapter, i) => (
          <ReportChapter key={chapter.id} chapter={chapter} index={i} />
        ))}
      </div>
    </div>
  );
}
