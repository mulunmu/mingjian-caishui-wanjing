import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import useReportStore from '@/stores/reportStore';
import Button from '@/components/ui/Button';
import Skeleton from '@/components/ui/Skeleton';
import Card from '@/components/ui/Card';

/** 报告详情：以 PDF 为交付物，不内嵌伪造章节分数。 */
export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentReport, fetchReport, downloadPdf, isLoadingList, reportList, fetchReportList } =
    useReportStore();
  const [loadError, setLoadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoadError(null);
    void (async () => {
      try {
        await fetchReport(id);
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : '报告加载失败');
      }
    })();
    if (reportList.length === 0) void fetchReportList();
  }, [id, fetchReport, fetchReportList, reportList.length]);

  const listItem = reportList.find((r) => r.report_id === id);
  const title = currentReport?.title || listItem?.title || id;
  const date = currentReport?.generated_at || listItem?.date;

  if (!id) {
    return (
      <div className="max-w-3xl mx-auto py-8 px-4">
        <p className="text-warm-500">未指定报告 ID</p>
      </div>
    );
  }

  if (!currentReport && !listItem && !loadError && isLoadingList) {
    return (
      <div className="max-w-3xl mx-auto py-8 px-4 space-y-4">
        <Skeleton height="32px" width="60%" />
        <Skeleton height="16px" width="40%" />
        <Skeleton height="120px" />
      </div>
    );
  }

  if (loadError && !listItem && !currentReport) {
    return (
      <div className="max-w-3xl mx-auto py-8 px-4 space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/report')}>
          返回报告中心
        </Button>
        <p className="text-terracotta text-sm">{loadError}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto pt-4 px-4 space-y-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/report')}
          icon={
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5" />
              <path d="M12 19l-7-7 7-7" />
            </svg>
          }
        >
          返回报告中心
        </Button>

        <Card className="p-6 space-y-3">
          <h1 className="text-xl font-semibold text-warm-800">{title}</h1>
          {date && <p className="text-sm text-warm-500">生成日期：{date}</p>}
          <p className="text-sm text-warm-600 leading-relaxed">
            {currentReport?.summary ||
              '报告已生成。完整内容以 PDF 交付，请下载查看（不展示内嵌演示章节）。'}
          </p>
          <div className="flex gap-3 pt-2">
            <Button
              disabled={downloading}
              onClick={async () => {
                setDownloading(true);
                try {
                  await downloadPdf(id);
                } finally {
                  setDownloading(false);
                }
              }}
            >
              {downloading ? '下载中…' : '下载 PDF'}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
