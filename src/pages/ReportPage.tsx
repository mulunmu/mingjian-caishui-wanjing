import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import useReportStore from '@/stores/reportStore';
import useAuthStore from '@/stores/authStore';
import { needsUpgrade } from '@/utils/plan';
import UpgradeModal from '@/components/ui/UpgradeModal';
import Button from '@/components/ui/Button';
import Skeleton from '@/components/ui/Skeleton';
import Card from '@/components/ui/Card';
import { translateTrace, translateSource } from '@/utils/trace';
import type { ReportChapter, ReportKpi } from '@/types/report';

/** 报告详情：结构化回读（与下载 PDF 同源快照）。章节/KPI 均来自后端，不伪造。 */
export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentReport, fetchReport, downloadPdf, isLoadingList, reportList, fetchReportList } =
    useReportStore();
  const user = useAuthStore((s) => s.user);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [showUpgrade, setShowUpgrade] = useState(false);

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

  const kpis: ReportKpi[] = currentReport?.kpis || [];
  const chapters: ReportChapter[] = currentReport?.chapters || [];

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto pt-4 px-4 space-y-4 pb-8">
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
          <div>
            <h1 className="text-xl font-semibold text-warm-800">{title}</h1>
            {currentReport?.subtitle && (
              <p className="text-sm text-warm-500 mt-1">{currentReport.subtitle}</p>
            )}
            {date && <p className="text-xs text-warm-400 mt-1">生成日期：{date}</p>}
          </div>

          {kpis.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {kpis.map((k) => (
                <div
                  key={k.label}
                  className="min-w-[96px] rounded-lg border border-warm-200 bg-warm-50 px-3 py-2"
                >
                  <div className="text-[11px] text-warm-400">{k.label}</div>
                  <div className="text-base font-semibold text-warm-800">
                    {k.value}
                    {k.unit && <span className="text-[10px] font-normal text-warm-400 ml-0.5">{k.unit}</span>}
                  </div>
                  {k.source && (
                    <div className="text-[10px] text-warm-300 mt-0.5 truncate" title={translateTrace(k.trace) || translateSource(k.source)}>
                      {translateSource(k.source)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {currentReport?.summary && (
            <p className="text-sm text-warm-600 leading-relaxed">{currentReport.summary}</p>
          )}

          <div className="flex gap-3 pt-2">
            <Button
              disabled={downloading}
              onClick={async () => {
                if (needsUpgrade(user)) {
                  setShowUpgrade(true);
                  return;
                }
                setDownloading(true);
                try {
                  await downloadPdf(id, currentReport?.title);
                } finally {
                  setDownloading(false);
                }
              }}
            >
              {downloading ? '下载中…' : '下载 PDF'}
            </Button>
          </div>
        </Card>

        {/* 结构化章节 */}
        {chapters.map((chapter, i) => (
          <Card key={chapter.id} className="p-6 space-y-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-amber/10 flex items-center justify-center text-amber text-sm font-semibold">
                {i + 1}
              </div>
              <div>
                <h3 className="text-base font-semibold text-warm-800">{chapter.title}</h3>
                {chapter.description && (
                  <p className="text-xs text-warm-400">{chapter.description}</p>
                )}
              </div>
              {chapter.risk_level && (
                <span className="ml-auto text-xs text-warm-500 border border-warm-200 rounded-full px-2 py-0.5">
                  {chapter.risk_level}
                </span>
              )}
            </div>

            {chapter.narration && (
              <p className="text-sm text-warm-500 italic">{chapter.narration}</p>
            )}

            {chapter.metrics && chapter.metrics.length > 0 && (
              <table className="w-full text-sm border-collapse">
                <tbody>
                  {chapter.metrics.map((m) => (
                    <tr key={m.label} className="border-b border-warm-100 last:border-0">
                      <td className="py-1.5 text-warm-500">{m.label}</td>
                      <td className="py-1.5 text-warm-800 text-right">
                        {m.value}
                        {m.unit && <span className="text-[10px] text-warm-400 ml-0.5">{m.unit}</span>}
                      </td>
                      {m.rating && (
                        <td className="py-1.5 text-warm-400 text-right text-xs">{m.rating}</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {chapter.points && chapter.points.length > 0 && (
              <div className="space-y-1">
                <h4 className="text-xs font-medium text-warm-500">风险点</h4>
                {chapter.points.map((p, j) => (
                  <p key={j} className="text-sm text-warm-700">· {p}</p>
                ))}
              </div>
            )}

            {chapter.advantages && chapter.advantages.length > 0 && (
              <div className="space-y-1">
                <h4 className="text-xs font-medium text-warm-500">优势</h4>
                {chapter.advantages.map((p, j) => (
                  <p key={j} className="text-sm text-warm-700">· {p}</p>
                ))}
              </div>
            )}

            {chapter.advice && chapter.advice.length > 0 && (
              <div className="space-y-1">
                <h4 className="text-xs font-medium text-warm-500">建议</h4>
                {chapter.advice.map((p, j) => (
                  <p key={j} className="text-sm text-warm-700">· {p}</p>
                ))}
              </div>
            )}

            {chapter.conclusion && (
              <div>
                <h4 className="text-xs font-medium text-warm-500 uppercase tracking-wider mb-1">
                  评估结论
                </h4>
                <p className="text-sm text-warm-700 leading-relaxed">{chapter.conclusion}</p>
              </div>
            )}

            {chapter.evidence_chain.length > 0 && (
              <div className="pt-1">
                <h4 className="text-xs font-medium text-warm-500 uppercase tracking-wider mb-1">
                  证据链 / 溯源
                </h4>
                <ul className="space-y-0.5">
                  {chapter.evidence_chain.map((e, j) => (
                    <li key={j} className="text-[11px] text-warm-400 font-mono">{translateTrace(e)}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        ))}

        {!currentReport?.summary && chapters.length === 0 && (
          <Card className="p-6">
            <p className="text-sm text-warm-500">
              该报告未留存结构化快照，完整内容请下载 PDF 查看。
            </p>
          </Card>
        )}
      </div>

      <UpgradeModal
        open={showUpgrade}
        onClose={() => setShowUpgrade(false)}
        feature="报告下载"
      />
    </div>
  );
}
