import { useState, useEffect, useCallback } from 'react';
import { FileText, Download, Eye, Calendar, Search, RefreshCw, Loader2, X, AlertTriangle } from 'lucide-react';
import useReportStore from '@/stores/reportStore';
import type { ReportListItem } from '@/types/report';
import client from '@/api/client';

export default function ReportCenter() {
  const { reportList, isLoadingList, listError, fetchReportList, downloadPdf } = useReportStore();
  const [searchTerm, setSearchTerm] = useState('');
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    void fetchReportList();
  }, [fetchReportList]);

  // 清理 blob URL
  useEffect(() => {
    return () => {
      if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    };
  }, [previewBlobUrl]);

  // 信任线：空列表/失败不回落伪造报告
  const reports = reportList;
  const filteredReports = reports.filter((r) => r.title.includes(searchTerm));

  /** 加载 HTML 预览 */
  const loadPreview = useCallback(async (report: ReportListItem) => {
    setPreviewLoading(true);
    setPreviewHtml(null);
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }

    try {
      // 用 scenario 从 report_id 中提取（格式 slice_{scenario}_{date}_{time}）
      const scenarioMatch = report.report_id.match(/^slice_([a-zA-Z0-9_-]+)_\d{8}_\d{6}$/);
      const scenario = scenarioMatch ? scenarioMatch[1] : 'general';

      const res = await client.post('/report/preview', {
        scenario,
        query: '预览报告',
      });

      // res 已被 axios 拦截器解包，可能是 HTML 字符串
      const html = typeof res === 'string' ? res : ((res.data as string) || String(res));
      setPreviewHtml(html);

      // 创建 blob URL 给 iframe
      const blob = new Blob([html], { type: 'text/html; charset=utf-8' });
      const url = URL.createObjectURL(blob);
      setPreviewBlobUrl(url);
    } catch {
      // preview 接口不可用时，用下载 URL 直接嵌入（部分浏览器支持 PDF iframe）
      setPreviewHtml(null);
      setPreviewBlobUrl(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewBlobUrl]);

  const handleView = (e: React.MouseEvent, report: ReportListItem) => {
    e.stopPropagation();
    setViewingId(report.report_id);
    loadPreview(report);
  };

  const handleClosePreview = () => {
    setViewingId(null);
    setPreviewHtml(null);
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
  };

  const handleDownload = async (e: React.MouseEvent, reportId: string) => {
    e.stopPropagation();
    await downloadPdf(reportId);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const activeReport = reports.find((r) => r.report_id === viewingId);

  return (
    <div className="h-full flex flex-col bg-warm-50">
      {/* 标题栏 */}
      <div className="bg-white border-b border-warm-200 px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-warm-800">报告中心</h1>
          <p className="text-xs text-warm-400 mt-0.5">查看和管理税务风险分析报告</p>
        </div>
        <button
          onClick={fetchReportList}
          disabled={isLoadingList}
          className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-warm-200 text-xs text-warm-600 hover:bg-warm-100 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoadingList ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      {/* 搜索栏 — 与左侧报告列表左对齐 */}
      <div className="bg-white border-b border-warm-200 py-2.5 flex">
        <div className="w-[420px] flex items-center gap-3 px-3 flex-shrink-0">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-warm-400" />
            <input
              type="text"
              placeholder="搜索报告..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full h-8 pl-9 pr-3 rounded-lg border border-warm-200 bg-warm-50 text-sm text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
            />
          </div>
          <span className="text-xs text-warm-400 flex-shrink-0">
            共 {filteredReports.length} 份
          </span>
        </div>
      </div>

      {/* 主体：列表 + 预览 */}
      <div className="flex-1 flex overflow-hidden justify-center">
        {/* 左侧：报告列表 */}
        <div className={`${viewingId ? 'w-[420px]' : 'flex-1 max-w-[600px] mx-auto'} flex-shrink-0 overflow-auto border-r border-warm-200 bg-white`}>
          <div className="p-3 space-y-1.5">
            {isLoadingList ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-5 h-5 text-warm-400 animate-spin" />
              </div>
            ) : listError ? (
              <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
                <AlertTriangle className="w-8 h-8 text-terracotta mb-3" />
                <p className="text-sm text-warm-700 font-medium">报告列表加载失败</p>
                <p className="text-xs text-warm-500 mt-1">{listError}</p>
                <button
                  type="button"
                  onClick={() => void fetchReportList()}
                  className="mt-3 h-8 px-3 rounded-lg border border-warm-200 text-xs text-warm-600 hover:bg-warm-50"
                >
                  重试
                </button>
              </div>
            ) : filteredReports.length > 0 ? (
              filteredReports.map((report) => {
                const isActive = viewingId === report.report_id;
                return (
                  <div
                    key={report.report_id}
                    onClick={(e) => handleView(e, report)}
                    className={`rounded-lg border p-3 cursor-pointer transition-all ${
                      isActive
                        ? 'border-amber-400 bg-amber-50/60 shadow-sm'
                        : 'border-transparent hover:bg-warm-50 hover:border-warm-200'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div className={`w-7 h-7 rounded flex items-center justify-center flex-shrink-0 ${
                        isActive ? 'bg-amber-500' : 'bg-warm-100'
                      }`}>
                        <FileText className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-warm-500'}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={`text-[13px] font-medium truncate ${isActive ? 'text-amber-800' : 'text-warm-700'}`}>
                          {report.title}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] text-warm-400">{report.date}</span>
                          <span className="text-[10px] text-warm-300">·</span>
                          <span className="text-[10px] text-warm-400">{formatSize(report.size)}</span>
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDownload(e, report.report_id)}
                        className="p-1 rounded hover:bg-warm-100 transition-colors flex-shrink-0"
                        title="下载"
                      >
                        <Download className="w-3.5 h-3.5 text-warm-400" />
                      </button>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="flex flex-col items-center py-16">
                <FileText className="w-10 h-10 text-warm-300 mb-2" />
                <p className="text-warm-400 text-sm">暂无报告</p>
              </div>
            )}
          </div>
        </div>

        {/* 右侧：预览区 */}
        {viewingId && (
          <div className="flex-1 flex flex-col bg-warm-100 min-w-0 max-w-[720px]">
            {/* 预览工具栏 */}
            <div className="bg-white border-b border-warm-200 px-4 py-2 flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <Eye size={13} className="text-warm-400 flex-shrink-0" />
                <span className="text-sm text-warm-600 truncate">
                  {activeReport?.title || '预览'}
                </span>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {activeReport && (
                  <button
                    onClick={() => window.open(activeReport.download_url || `/api/v1/report/${activeReport.report_id}/download`, '_blank')}
                    className="text-[11px] text-warm-500 hover:text-warm-700 px-2 py-1 rounded hover:bg-warm-100 transition-colors"
                  >
                    新窗口打开
                  </button>
                )}
                <button
                  onClick={handleClosePreview}
                  className="p-1 rounded hover:bg-warm-100 transition-colors"
                  title="关闭预览"
                >
                  <X size={14} className="text-warm-400" />
                </button>
              </div>
            </div>

            {/* 预览内容 */}
            <div className="flex-1 overflow-hidden">
              {previewLoading ? (
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="w-6 h-6 text-warm-400 animate-spin" />
                  <span className="ml-2 text-sm text-warm-500">加载预览...</span>
                </div>
              ) : previewBlobUrl ? (
                <iframe
                  src={previewBlobUrl}
                  className="w-full h-full border-0"
                  title="报告预览"
                />
              ) : previewHtml ? (
                <div
                  className="h-full overflow-auto p-6 bg-white"
                  dangerouslySetInnerHTML={{ __html: previewHtml }}
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full">
                  <FileText className="w-12 h-12 text-warm-300 mb-3" />
                  <p className="text-warm-400 text-sm">预览不可用</p>
                  <p className="text-warm-300 text-xs mt-1">请使用「新窗口打开」或下载查看</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
