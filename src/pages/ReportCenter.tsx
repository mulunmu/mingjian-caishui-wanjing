import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  FileText,
  Download,
  Eye,
  FilePlus2,
  Search,
  RefreshCw,
  Loader2,
  X,
  AlertTriangle,
  Sparkles,
  Trash2,
  Mail,
  MoreHorizontal,
} from 'lucide-react';
import useReportStore from '@/stores/reportStore';
import useAuthStore from '@/stores/authStore';
import { needsUpgrade } from '@/utils/plan';
import UpgradeModal from '@/components/ui/UpgradeModal';
import ReportWizard, { type WizardPrefs } from '@/components/report/ReportWizard';
import SendEmailModal from '@/components/report/SendEmailModal';
import type { ReportScenarioDef } from '@/constants/reportScenarios';
import type { ReportListItem } from '@/types/report';
import { reportApi } from '@/api/report';

function formatValidationWarn(validation: Record<string, unknown>): string {
  const parts = [
    '报告已生成，但未完全通过溯源校验（不可信表述已剥离）。请人工复核后再对外分发。',
  ];
  const nums: string[] = [];
  const unanchored = Number(validation.unanchored || 0);
  const numberUn = Number(validation.number_unanchored || 0);
  const risk = Number(validation.risk_contradictions || 0);
  if (unanchored) nums.push(`无溯源结论 ${unanchored}`);
  if (numberUn) nums.push(`无锚点数字句 ${numberUn}`);
  if (risk) nums.push(`风险话术矛盾 ${risk}`);
  const enf = validation.enforced as Record<string, unknown> | undefined;
  if (enf) {
    const dropped = Number(enf.dropped_claims || 0);
    const stripped = Number(enf.stripped_sentences || 0);
    if (dropped) nums.push(`已剥离结论 ${dropped}`);
    if (stripped) nums.push(`已剥离解读句 ${stripped}`);
  }
  const cross = validation.cross_surface as Record<string, unknown> | undefined;
  if (cross && cross.ok === false) nums.push('跨面数字未对齐');
  if (nums.length) parts.push(`明细：${nums.join('；')}。`);
  return parts.join('');
}

export default function ReportCenter() {
  const { reportList, isLoadingList, listError, fetchReportList, downloadPdf, generateSlice, deleteReport } =
    useReportStore();
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [showGenerate, setShowGenerate] = useState(false);
  const [generatingScenario, setGeneratingScenario] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [validationWarn, setValidationWarn] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [sendTarget, setSendTarget] = useState<{ ids: string[]; titles: string[] } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [searchParams] = useSearchParams();
  const highlightId = searchParams.get('highlight');
  const wizardParam = searchParams.get('wizard');

  useEffect(() => {
    void fetchReportList();
  }, [fetchReportList]);

  // 仅显式 ?wizard=1 时打开向导；落地页不再自动弹窗（刀 2b）
  useEffect(() => {
    if (wizardParam === '1') {
      setShowGenerate(true);
    }
  }, [wizardParam]);

  // 清理 blob URL
  useEffect(() => {
    return () => {
      if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    };
  }, [previewBlobUrl]);

  // 信任线：空列表/失败不回落伪造报告
  const reports = reportList;
  const filteredReports = reports.filter((r) => r.title.includes(searchTerm));

  /** 加载预览：直接渲染已保存的 PDF 快照（与「下载」同一文件），不重算报告。
   *  避免数据接入后重算导致预览与下载内容漂移（快照一致性）。 */
  const loadPreview = useCallback(async (report: ReportListItem) => {
    setPreviewLoading(true);
    setPreviewFailed(false);
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }

    try {
      const blob = await reportApi.downloadPdf(report.report_id);
      const url = URL.createObjectURL(blob);
      setPreviewBlobUrl(url);
    } catch {
      setPreviewBlobUrl(null);
      setPreviewFailed(true);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewBlobUrl]);

  // 个体页生成后跳转带 ?highlight=<reportId> → 自动选中并预览
  useEffect(() => {
    if (!highlightId || viewingId || isLoadingList) return;
    const item = reportList.find((r) => r.report_id === highlightId);
    if (item) {
      setViewingId(item.report_id);
      loadPreview(item);
    }
  }, [highlightId, viewingId, isLoadingList, reportList, loadPreview]);

  const handleView = (e: React.MouseEvent, report: ReportListItem) => {
    e.stopPropagation();
    setViewingId(report.report_id);
    loadPreview(report);
  };

  const handleClosePreview = () => {
    setViewingId(null);
    setPreviewFailed(false);
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
  };

  const handleDownload = async (e: React.MouseEvent, report: ReportListItem) => {
    e.stopPropagation();
    if (needsUpgrade(user)) {
      setShowUpgrade(true);
      return;
    }
    await downloadPdf(report.report_id, report.title);
  };

  const handleDelete = async (e: React.MouseEvent, report: ReportListItem) => {
    e.stopPropagation();
    if (!window.confirm(`确定删除报告「${report.title}」吗？删除后不可恢复。`)) return;
    setDeletingId(report.report_id);
    try {
      await deleteReport(report.report_id);
      if (viewingId === report.report_id) handleClosePreview();
      setSelectedIds((ids) => ids.filter((id) => id !== report.report_id));
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setDeletingId(null);
    }
  };

  const handleSend = (e: React.MouseEvent, report: ReportListItem) => {
    e.stopPropagation();
    setSendTarget({ ids: [report.report_id], titles: [report.title] });
  };

  const toggleSelect = (e: React.ChangeEvent<HTMLInputElement>, reportId: string) => {
    e.stopPropagation();
    setSelectedIds((ids) =>
      ids.includes(reportId) ? ids.filter((id) => id !== reportId) : [...ids, reportId]
    );
  };

  const handleBatchSend = () => {
    const selected = reports.filter((r) => selectedIds.includes(r.report_id));
    if (selected.length === 0) return;
    setSendTarget({ ids: selected.map((r) => r.report_id), titles: selected.map((r) => r.title) });
  };

  /** 向导完成 → 生成切片报告；付费模块 / 非定制用户触发升级提示 */
  const handleWizardConfirm = async (scenario: ReportScenarioDef, prefs: WizardPrefs) => {
    if (needsUpgrade(user)) {
      setShowUpgrade(true);
      return;
    }
    setGeneratingScenario(scenario.key);
    setGenerateError(null);
    setValidationWarn(null);
    try {
      let reportId: string;
      let validation: Record<string, unknown> | undefined;
      if (prefs.enterprise_id) {
        // 单企业通道：指定企业 → 走个体深度报告（脱敏、无 LLM）
        const res = await reportApi.enterprise(prefs.enterprise_id);
        reportId = res.report_id;
        validation = res.validation as Record<string, unknown> | undefined;
      } else {
        const out = await generateSlice({
          scenario: scenario.key,
          industry_l1: prefs.industry_l1 || undefined,
        });
        reportId = out.reportId;
        validation = out.validation as Record<string, unknown> | undefined;
      }
      await fetchReportList();
      // 选中并预览新生成的报告
      const item = useReportStore.getState().reportList.find((r) => r.report_id === reportId);
      setShowGenerate(false);
      if (validation && validation.ok === false) {
        setValidationWarn(formatValidationWarn(validation));
      }
      if (item) {
        setViewingId(reportId);
        loadPreview(item);
      }
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : '报告生成失败，请稍后重试');
    } finally {
      setGeneratingScenario(null);
    }
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
          <h1 className="text-lg font-semibold text-warm-800">出报告</h1>
          <p className="text-xs text-warm-400 mt-0.5">选场景生成风控报告 · 查看与管理已出报告</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setGenerateError(null);
              setShowGenerate(true);
            }}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg bg-amber text-white text-xs hover:bg-amber-dark transition-colors"
          >
            <FilePlus2 className="w-3.5 h-3.5" />
            生成报告
          </button>
          <button
            onClick={() => navigate('/research?custom=1')}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-amber/30 text-amber text-xs hover:bg-amber-50 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            AI 定制报告
          </button>
          <button
            onClick={fetchReportList}
            disabled={isLoadingList}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-warm-200 text-xs text-warm-600 hover:bg-warm-100 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingList ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
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

      {selectedIds.length > 0 && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-center gap-3">
          <span className="text-xs text-warm-700">已选 {selectedIds.length} 份</span>
          <button
            onClick={handleBatchSend}
            className="flex items-center gap-1.5 h-7 px-3 rounded-lg bg-amber text-white text-xs hover:bg-amber-dark transition-colors"
          >
            <Mail className="w-3.5 h-3.5" />
            批量发送
          </button>
          <button
            onClick={() => setSelectedIds([])}
            className="h-7 px-3 rounded-lg border border-warm-200 text-xs text-warm-500 hover:bg-warm-100 transition-colors"
          >
            取消选择
          </button>
        </div>
      )}

      {validationWarn && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-amber mt-0.5 flex-shrink-0" />
          <p className="text-xs text-warm-700 flex-1">{validationWarn}</p>
          <button
            type="button"
            onClick={() => setValidationWarn(null)}
            className="text-warm-400 hover:text-warm-600"
            aria-label="关闭提示"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 主体：列表 + 预览 */}
      <div className="flex-1 flex overflow-hidden justify-center">
        {/* 左侧：报告列表 */}
        <div className={`${viewingId ? 'w-[420px]' : 'flex-1 max-w-[600px] mx-auto'} flex-shrink-0 overflow-auto border-r border-warm-200 bg-white`}>
          <div className="p-4 space-y-3">
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
                const menuOpen = menuOpenId === report.report_id;
                return (
                  <div
                    key={report.report_id}
                    onClick={(e) => {
                      setMenuOpenId(null);
                      handleView(e, report);
                    }}
                    className={`rounded-xl border p-4 cursor-pointer transition-all ${
                      isActive
                        ? 'border-amber-400 bg-amber-50/60 shadow-sm'
                        : 'border-warm-100 hover:bg-warm-50 hover:border-warm-200'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(report.report_id)}
                        onChange={(e) => toggleSelect(e, report.report_id)}
                        onClick={(e) => e.stopPropagation()}
                        className="accent-amber flex-shrink-0"
                      />
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          isActive ? 'bg-amber-500' : 'bg-warm-100'
                        }`}
                      >
                        <FileText
                          className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-warm-500'}`}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p
                          className={`text-[13px] font-medium truncate ${
                            isActive ? 'text-amber-800' : 'text-warm-700'
                          }`}
                        >
                          {report.title}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] text-warm-400">{report.date}</span>
                          <span className="text-[10px] text-warm-300">·</span>
                          <span className="text-[10px] text-warm-400">
                            {formatSize(report.size)}
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/report/${report.report_id}`);
                        }}
                        className="p-1.5 rounded-lg hover:bg-warm-100 transition-colors flex-shrink-0"
                        title="查看详情"
                      >
                        <Eye className="w-3.5 h-3.5 text-warm-400" />
                      </button>
                      <div className="relative flex-shrink-0">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(menuOpen ? null : report.report_id);
                          }}
                          className="p-1.5 rounded-lg hover:bg-warm-100 transition-colors"
                          title="更多操作"
                          aria-label="更多操作"
                        >
                          <MoreHorizontal className="w-3.5 h-3.5 text-warm-400" />
                        </button>
                        {menuOpen && (
                          <div
                            className="absolute right-0 top-full mt-1 z-20 w-36 rounded-lg border border-warm-200 bg-white shadow-md py-1"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              type="button"
                              onClick={(e) => {
                                setMenuOpenId(null);
                                handleDownload(e, report);
                              }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-warm-700 hover:bg-warm-50"
                            >
                              <Download className="w-3.5 h-3.5" />
                              下载
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                setMenuOpenId(null);
                                handleSend(e, report);
                              }}
                              className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-warm-700 hover:bg-warm-50"
                            >
                              <Mail className="w-3.5 h-3.5" />
                              发送邮件
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                setMenuOpenId(null);
                                handleDelete(e, report);
                              }}
                              disabled={deletingId === report.report_id}
                              className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs text-terracotta hover:bg-terracotta/5 disabled:opacity-50"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              删除
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="flex flex-col items-center py-16 px-6 text-center">
                <FileText className="w-10 h-10 text-warm-300 mb-2" />
                <p className="text-warm-400 text-sm">暂无报告</p>
                {needsUpgrade(user) && (
                  <button
                    onClick={() => setShowUpgrade(true)}
                    className="mt-3 h-8 px-3 rounded-lg border border-amber-300 text-xs text-amber-600 hover:bg-amber-50 transition-colors"
                  >
                    了解定制报告权限
                  </button>
                )}
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
                    onClick={() => {
                      if (needsUpgrade(user)) {
                        setShowUpgrade(true);
                        return;
                      }
                      window.open(activeReport.download_url || `/api/v1/report/${activeReport.report_id}/download`, '_blank');
                    }}
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
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="flex flex-col items-center justify-center h-full">
                  <FileText className="w-12 h-12 text-warm-300 mb-3" />
                  <p className="text-warm-400 text-sm">{previewFailed ? '预览加载失败' : '预览不可用'}</p>
                  <p className="text-warm-300 text-xs mt-1">请使用「新窗口打开」或下载查看</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <ReportWizard
        open={showGenerate}
        onClose={() => setShowGenerate(false)}
        onConfirm={handleWizardConfirm}
        busy={generatingScenario !== null}
        error={generateError}
        onOpenCustom={() => navigate('/research?custom=1')}
      />

      <UpgradeModal
        open={showUpgrade}
        onClose={() => setShowUpgrade(false)}
        feature="报告生成 / 下载"
      />

      <SendEmailModal
        open={sendTarget !== null}
        onClose={() => setSendTarget(null)}
        reportIds={sendTarget?.ids ?? []}
        titles={sendTarget?.titles ?? []}
      />
    </div>
  );
}
