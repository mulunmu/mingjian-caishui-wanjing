import { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload,
  FileSpreadsheet,
  ArrowRight,
  ArrowLeft,
  Check,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Link as LinkIcon,
} from 'lucide-react';
import { ingestApi } from '@/api/risk';
import Card from '@/components/ui/Card';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import Divider from '@/components/ui/Divider';
import Skeleton from '@/components/ui/Skeleton';
import useOverviewStore from '@/stores/overviewStore';

/* ── 类型 ── */
interface MappingItem {
  source_column: string;
  target_field: string | null;
  confidence?: number;
  suggested_fields?: string[];
}

interface StepConfig {
  key: string;
  label: string;
  icon: React.ReactNode;
}

/* ── 步骤配置 ── */
const steps: StepConfig[] = [
  { key: 'upload', label: '上传数据', icon: <Upload className="w-4 h-4" /> },
  { key: 'mapping', label: '字段映射', icon: <LinkIcon className="w-4 h-4" /> },
  { key: 'confirm', label: '确认导入', icon: <Check className="w-4 h-4" /> },
];

/* ── 常见目标字段选项 ── */
const commonTargetFields = [
  'enterprise_id',
  'display_label',
  'industry_l1',
  'province',
  'period',
  'revenue',
  'cost',
  'profit',
  'tax_paid',
  'vat_output',
  'vat_input',
  'total_assets',
  'total_liabilities',
  'employee_count',
  'social_security_count',
  'credit_level',
  'invoice_count',
  'red_invoice_count',
  'purchase_amount',
  'sales_amount',
];

export default function DataIngestPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [columns, setColumns] = useState<string[]>([]);
  const [rawInput, setRawInput] = useState('');
  const [mappings, setMappings] = useState<MappingItem[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [ingestResult, setIngestResult] = useState<Record<string, unknown> | null>(null);
  const [mode, setMode] = useState<'temporary' | 'permanent'>('temporary');
  const [identityField, setIdentityField] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  /* ── 解析 CSV 表头 ── */
  const parseCsvHeaders = (text: string): string[] => {
    const firstLine = text.split('\n')[0].trim();
    if (!firstLine) return [];
    // 支持逗号、分号、制表符分隔
    const delimiter = firstLine.includes('\t') ? '\t' : firstLine.includes(';') ? ';' : ',';
    return firstLine
      .split(delimiter)
      .map((h) => h.trim().replace(/^["']|["']$/g, ''))
      .filter(Boolean);
  };

  /* ── 处理文件上传 ── */
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      const headers = parseCsvHeaders(text);
      if (headers.length === 0) {
        setError('无法解析文件表头，请检查文件格式');
        return;
      }
      setColumns(headers);
      // 保存原始内容以便后续行数据上传
      setRawInput(text);
    };
    reader.onerror = () => setError('文件读取失败');
    reader.readAsText(file);
  };

  /* ── 处理粘贴表头 ── */
  const handlePasteHeaders = () => {
    setError(null);
    const headers = parseCsvHeaders(rawInput);
    if (headers.length === 0) {
      setError('未检测到有效表头，请输入以逗号分隔的列名');
      return;
    }
    setColumns(headers);
  };

  /* ── Step 1 → 2: 调用 map 接口 ── */
  const handleMapColumns = async () => {
    if (columns.length === 0) {
      setError('请先上传数据或输入表头');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const res = await ingestApi.mapColumns(columns);
      // 假设后端返回 { mappings: MappingItem[], session_id?: string }
      const data = res as Record<string, unknown>;
      const mappingList = (data.mappings || data.data || res) as MappingItem[] | Record<string, unknown>;
      if (Array.isArray(mappingList)) {
        setMappings(
          mappingList.map((m: MappingItem) => ({
            source_column: m.source_column,
            target_field: m.target_field ?? null,
            confidence: m.confidence,
            suggested_fields: m.suggested_fields || [],
          }))
        );
      } else {
        // 如果返回格式不同，用列名生成初始映射
        setMappings(
          columns.map((col) => ({
            source_column: col,
            target_field: null,
            suggested_fields: [],
          }))
        );
      }
      if (data.session_id) setSessionId(data.session_id as string);
      setCurrentStep(1);
    } catch {
      // 自动映射不可用 → 降级为手动映射，但明确告知，不静默放行
      setError('自动字段映射暂不可用，已切换为手动配置，请逐列选择目标字段。');
      setMappings(
        columns.map((col) => ({
          source_column: col,
          target_field: null,
          suggested_fields: [],
        }))
      );
      setCurrentStep(1);
    } finally {
      setIsLoading(false);
    }
  };

  /* ── 更新映射目标字段 ── */
  const updateMapping = (index: number, targetField: string | null) => {
    setMappings((prev) =>
      prev.map((m, i) => (i === index ? { ...m, target_field: targetField } : m))
    );
  };

  /* ── Step 2 → 3: 调用 commit 接口 ── */
  const handleCommit = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const commitMappings = mappings.map((m) => ({
        source_column: m.source_column,
        target_field: m.target_field,
      }));
      const res = await ingestApi.commit(commitMappings, mode, sessionId);
      const data = res as Record<string, unknown>;
      if (data.session_id) setSessionId(data.session_id as string);
      setCurrentStep(2);
    } catch {
      // commit 失败不再静默放行：明确报错，留在本步供重试
      setError('映射提交失败，请检查字段选择后重试。');
    } finally {
      setIsLoading(false);
    }
  };

  /* ── Step 3: 调用 rows 接口写入数据 ── */
  const handleIngestRows = async () => {
    setIsLoading(true);
    setError(null);
    setSuccessMsg(null);
    try {
      // 身份字段（唯一键）必填：后端据此派生 MD5 enterprise_id，明文不落库
      if (!identityField) {
        setError('请先选择身份字段（税号/企业名/统一编号），用于生成匿名样本编号');
        setIsLoading(false);
        return;
      }

      // 从原始输入解析行数据
      const lines = rawInput.split('\n').filter((l) => l.trim());
      if (lines.length < 2) {
        setError('数据不足，至少需要表头和一行数据');
        setIsLoading(false);
        return;
      }
      const delimiter = lines[0].includes('\t') ? '\t' : lines[0].includes(';') ? ';' : ',';
      const headers = lines[0].split(delimiter).map((h) => h.trim().replace(/^["']|["']$/g, ''));
      const rows = lines.slice(1).map((line) => {
        const values = line.split(delimiter).map((v) => v.trim().replace(/^["']|["']$/g, ''));
        const row: Record<string, unknown> = {};
        headers.forEach((h, i) => {
          row[h] = values[i] ?? '';
        });
        return row;
      });

      const commitMappings = mappings.map((m) => ({
        source_column: m.source_column,
        target_field: m.target_field,
      }));

      const res = await ingestApi.ingestRows({
        session_id: sessionId,
        identity_field: identityField,
        mappings: commitMappings,
        rows,
        mode,
      });

      const ingested =
        typeof res.ingested === 'number'
          ? res.ingested
          : typeof res.rows_processed === 'number'
            ? res.rows_processed
            : null;
      if (ingested == null) {
        setError('导入结果未返回成功行数，请核对服务端响应后再确认。');
        setIngestResult(res as Record<string, unknown>);
        return;
      }
      setIngestResult(res as Record<string, unknown>);
      setSuccessMsg(`成功导入 ${ingested} 行数据`);
      // 数据接入状态同步：永久导入会写入 core_metrics，刷新总览使 Header/Footer/看板样本数一致
      void useOverviewStore.getState().fetchOverview();
    } catch (e) {
      setSuccessMsg(null);
      setIngestResult(null);
      setError(e instanceof Error ? e.message : '数据提交失败，请稍后重试。');
    } finally {
      setIsLoading(false);
    }
  };

  /* ── 重置 ── */
  const handleReset = () => {
    setCurrentStep(0);
    setColumns([]);
    setRawInput('');
    setMappings([]);
    setSessionId(undefined);
    setError(null);
    setSuccessMsg(null);
    setIngestResult(null);
    setMode('temporary');
    setIdentityField(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="h-full flex flex-col bg-warm-50">
      {/* 页面标题 */}
      <div className="bg-white border-b border-warm-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-warm-800">数据接入</h1>
          <p className="text-sm text-warm-500 mt-1">
            上传 CSV/Excel 做字段映射与导入演示；完整财税票 ETL 与引擎重算需走后端管道，本页不替代全量入库。
          </p>
        </div>
        <button
          onClick={handleReset}
          className="flex items-center gap-2 h-9 px-3 rounded-lg border border-warm-200 text-sm text-warm-600 hover:bg-warm-100 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          重置
        </button>
      </div>

      {/* 步骤指示器 */}
      <div className="bg-white border-b border-warm-200 px-6 py-3">
        <div className="max-w-4xl mx-auto flex items-center gap-2">
          {steps.map((step, i) => (
            <div key={step.key} className="flex items-center gap-2">
              <div
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                  i === currentStep
                    ? 'bg-amber/10 text-amber border border-amber'
                    : i < currentStep
                    ? 'bg-sage/10 text-sage border border-sage/30'
                    : 'bg-warm-100 text-warm-400 border border-warm-200'
                }`}
              >
                {i < currentStep ? <Check className="w-3.5 h-3.5" /> : step.icon}
                {step.label}
              </div>
              {i < steps.length - 1 && (
                <ArrowRight className="w-4 h-4 text-warm-300 mx-1" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto">
          {/* 错误提示 */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="mb-4 flex items-center gap-2 px-4 py-3 bg-terracotta/5 border border-terracotta/20 rounded-lg"
              >
                <AlertTriangle className="w-4 h-4 text-terracotta flex-shrink-0" />
                <span className="text-sm text-terracotta">{error}</span>
                <button onClick={() => setError(null)} className="ml-auto text-terracotta/60 hover:text-terracotta">
                  ×
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* 成功提示 */}
          <AnimatePresence>
            {successMsg && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="mb-4 flex items-center gap-2 px-4 py-3 bg-sage/5 border border-sage/20 rounded-lg"
              >
                <CheckCircle2 className="w-4 h-4 text-sage flex-shrink-0" />
                <span className="text-sm text-sage">{successMsg}</span>
                <button onClick={() => setSuccessMsg(null)} className="ml-auto text-sage/60 hover:text-sage">
                  ×
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence mode="wait">
            {/* ── Step 0: 上传数据 ── */}
            {currentStep === 0 && (
              <motion.div
                key="upload"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.25 }}
                className="space-y-4"
              >
                {/* 文件上传 */}
                <Card index={0} className="p-6">
                  <h3 className="text-sm font-semibold text-warm-700 mb-4">方式一：上传 CSV 文件</h3>
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className="border-2 border-dashed border-warm-200 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:border-amber hover:bg-amber/5 transition-colors"
                  >
                    <FileSpreadsheet className="w-10 h-10 text-warm-300 mb-3" />
                    <p className="text-sm text-warm-600 font-medium">点击选择 CSV 文件</p>
                    <p className="text-xs text-warm-400 mt-1">支持 .csv 格式，首行为表头</p>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.txt,.tsv"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                  {columns.length > 0 && (
                    <div className="mt-4">
                      <p className="text-xs text-warm-500 mb-2">已识别 {columns.length} 列：</p>
                      <div className="flex flex-wrap gap-1.5">
                        {columns.map((col) => (
                          <span
                            key={col}
                            className="px-2 py-1 text-xs bg-warm-100 text-warm-700 rounded-md font-mono"
                          >
                            {col}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>

                {/* 粘贴表头 */}
                <Card index={1} className="p-6">
                  <h3 className="text-sm font-semibold text-warm-700 mb-4">方式二：粘贴表头或数据</h3>
                  <textarea
                    value={rawInput}
                    onChange={(e) => setRawInput(e.target.value)}
                    placeholder={'粘贴 CSV 表头或完整数据，例如：\nenterprise_id,industry,revenue,tax_paid\nENT001,制造业,1500000,45000'}
                    rows={5}
                    className="w-full px-3 py-2 text-sm bg-white border border-warm-200 rounded-lg text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber resize-none font-mono"
                  />
                  <div className="mt-3 flex items-center gap-3">
                    <Button variant="secondary" size="sm" onClick={handlePasteHeaders}>
                      解析表头
                    </Button>
                    {columns.length > 0 && (
                      <span className="text-xs text-sage">已识别 {columns.length} 列</span>
                    )}
                  </div>
                </Card>

                {/* 下一步 */}
                {columns.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex justify-end"
                  >
                    <Button
                      onClick={handleMapColumns}
                      loading={isLoading}
                      icon={<ArrowRight className="w-4 h-4" />}
                    >
                      下一步：字段映射
                    </Button>
                  </motion.div>
                )}
              </motion.div>
            )}

            {/* ── Step 1: 字段映射 ── */}
            {currentStep === 1 && (
              <motion.div
                key="mapping"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.25 }}
                className="space-y-4"
              >
                <Card index={0} className="p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-warm-700">字段映射配置</h3>
                    <span className="text-xs text-warm-400">
                      将源列映射到系统字段，未映射的列将被忽略
                    </span>
                  </div>

                  {isLoading ? (
                    <div className="space-y-3">
                      {[1, 2, 3].map((i) => (
                        <Skeleton key={i} height="56px" />
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {/* 表头行 */}
                      <div className="grid grid-cols-12 gap-3 px-3 py-2 text-xs font-medium text-warm-500 bg-warm-50 rounded-lg">
                        <div className="col-span-4">源列名</div>
                        <div className="col-span-1 text-center">→</div>
                        <div className="col-span-5">目标字段</div>
                        <div className="col-span-2">状态</div>
                      </div>

                      {mappings.map((mapping, i) => (
                        <motion.div
                          key={mapping.source_column}
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          transition={{ delay: i * 0.03 }}
                          className="grid grid-cols-12 gap-3 items-center px-3 py-2.5 border border-warm-100 rounded-lg hover:border-warm-200 transition-colors"
                        >
                          {/* 源列名 */}
                          <div className="col-span-4">
                            <span className="text-sm text-warm-800 font-mono bg-warm-50 px-2 py-0.5 rounded">
                              {mapping.source_column}
                            </span>
                          </div>

                          {/* 箭头 */}
                          <div className="col-span-1 flex justify-center">
                            <ArrowRight className="w-4 h-4 text-warm-300" />
                          </div>

                          {/* 目标字段选择 */}
                          <div className="col-span-5">
                            <select
                              value={mapping.target_field || ''}
                              onChange={(e) =>
                                updateMapping(i, e.target.value || null)
                              }
                              className="w-full h-8 px-2 rounded-md border border-warm-200 bg-white text-sm text-warm-700 focus:outline-none focus:border-amber"
                            >
                              <option value="">-- 跳过此列 --</option>
                              {commonTargetFields.map((field) => (
                                <option key={field} value={field}>
                                  {field}
                                </option>
                              ))}
                              {/* 如果有建议字段，优先显示 */}
                              {mapping.suggested_fields
                                ?.filter((f) => !commonTargetFields.includes(f))
                                .map((field) => (
                                  <option key={field} value={field}>
                                    {field} (建议)
                                  </option>
                                ))}
                            </select>
                          </div>

                          {/* 状态 */}
                          <div className="col-span-2">
                            {mapping.target_field ? (
                              <Badge level="low">已映射</Badge>
                            ) : (
                              <Badge level="info">跳过</Badge>
                            )}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  )}
                </Card>

                {/* 导入配置：身份字段 + 模式 */}
                <Card index={1} className="p-6">
                  <h3 className="text-sm font-semibold text-warm-700 mb-4">导入配置</h3>

                  <div className="mb-4">
                    <label className="block text-xs text-warm-500 mb-1.5">
                      身份字段（唯一键）
                    </label>
                    <select
                      value={identityField || ''}
                      onChange={(e) => setIdentityField(e.target.value || null)}
                      className="w-full h-9 px-2 rounded-md border border-warm-200 bg-white text-sm text-warm-700 focus:outline-none focus:border-amber"
                    >
                      <option value="">-- 请选择唯一标识列 --</option>
                      {columns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-warm-400 mt-1">
                      用于派生匿名样本编号（MD5），明文身份不落库
                    </p>
                  </div>

                  <div>
                    <span className="block text-xs text-warm-500 mb-1.5">导入模式</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setMode('temporary')}
                        className={`flex-1 h-9 rounded-md border text-sm transition-colors ${
                          mode === 'temporary'
                            ? 'border-amber bg-amber/5 text-amber'
                            : 'border-warm-200 text-warm-600 hover:bg-warm-100'
                        }`}
                      >
                        会话内预览
                      </button>
                      <button
                        type="button"
                        onClick={() => setMode('permanent')}
                        className={`flex-1 h-9 rounded-md border text-sm transition-colors ${
                          mode === 'permanent'
                            ? 'border-sage bg-sage/5 text-sage'
                            : 'border-warm-200 text-warm-600 hover:bg-warm-100'
                        }`}
                      >
                        永久写入
                      </button>
                    </div>
                    <p className="text-xs text-warm-400 mt-1">
                      {mode === 'permanent'
                        ? '写入正式库，导入后全局样本数与报告随之更新'
                        : '仅本次会话内可用，不改变正式库数据'}
                    </p>
                  </div>
                </Card>

                {/* 操作按钮 */}
                <div className="flex items-center justify-between">
                  <Button
                    variant="ghost"
                    onClick={() => setCurrentStep(0)}
                    icon={<ArrowLeft className="w-4 h-4" />}
                  >
                    上一步
                  </Button>
                  <Button
                    onClick={handleCommit}
                    loading={isLoading}
                    icon={<ArrowRight className="w-4 h-4" />}
                  >
                    确认映射
                  </Button>
                </div>
              </motion.div>
            )}

            {/* ── Step 2: 确认导入 ── */}
            {currentStep === 2 && (
              <motion.div
                key="confirm"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.25 }}
                className="space-y-4"
              >
                <Card index={0} className="p-6">
                  <h3 className="text-sm font-semibold text-warm-700 mb-4">确认导入</h3>

                  {/* 映射摘要 */}
                  <div className="mb-4">
                    <p className="text-xs text-warm-500 mb-2">字段映射摘要：</p>
                    <div className="flex flex-wrap gap-1.5">
                      {mappings
                        .filter((m) => m.target_field)
                        .map((m) => (
                          <span
                            key={m.source_column}
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-amber/5 text-amber border border-amber/20 rounded-md"
                          >
                            <span className="font-mono text-warm-500">{m.source_column}</span>
                            <ArrowRight className="w-3 h-3" />
                            <span className="font-mono font-medium">{m.target_field}</span>
                          </span>
                        ))}
                    </div>
                    {mappings.filter((m) => m.target_field).length === 0 && (
                      <p className="text-xs text-warm-400">未选择任何映射字段</p>
                    )}
                  </div>

                  <Divider className="my-4" />

                  {/* 数据源信息 */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-xs text-warm-400">源列数</span>
                      <p className="text-lg font-bold text-warm-800">{columns.length}</p>
                    </div>
                    <div>
                      <span className="text-xs text-warm-400">已映射字段</span>
                      <p className="text-lg font-bold text-warm-800">
                        {mappings.filter((m) => m.target_field).length}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 mt-4">
                    <div>
                      <span className="text-xs text-warm-400">身份字段</span>
                      <p className="text-sm font-medium text-warm-800">{identityField || '未选择'}</p>
                    </div>
                    <div>
                      <span className="text-xs text-warm-400">导入模式</span>
                      <p className="text-sm font-medium text-warm-800">
                        {mode === 'permanent' ? '永久写入' : '会话内预览'}
                      </p>
                    </div>
                  </div>
                </Card>

                {/* 导入结果 */}
                {ingestResult && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <Card index={2} className="p-6 border-sage/30 bg-sage/5">
                      <div className="flex items-center gap-2 mb-3">
                        <CheckCircle2 className="w-5 h-5 text-sage" />
                        <h3 className="text-sm font-semibold text-sage">导入完成</h3>
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        {(ingestResult.ingested !== undefined ||
                          ingestResult.rows_processed !== undefined) && (
                          <div>
                            <span className="text-xs text-warm-400">处理行数</span>
                            <p className="text-lg font-bold text-warm-800">
                              {String(ingestResult.ingested ?? ingestResult.rows_processed)}
                            </p>
                          </div>
                        )}
                        {(ingestResult.mode !== undefined || ingestResult.status !== undefined) && (
                          <div>
                            <span className="text-xs text-warm-400">模式</span>
                            <p className="text-lg font-bold text-warm-800">
                              {String(ingestResult.mode ?? ingestResult.status)}
                            </p>
                          </div>
                        )}
                      </div>
                    </Card>
                  </motion.div>
                )}

                {/* 操作按钮 */}
                <div className="flex items-center justify-between">
                  <Button
                    variant="ghost"
                    onClick={() => setCurrentStep(1)}
                    icon={<ArrowLeft className="w-4 h-4" />}
                  >
                    上一步
                  </Button>
                  <div className="flex items-center gap-3">
                    {!ingestResult && (
                      <Button
                        onClick={handleIngestRows}
                        loading={isLoading}
                        icon={<Upload className="w-4 h-4" />}
                      >
                        提交数据
                      </Button>
                    )}
                    {ingestResult && (
                      <Button
                        variant="secondary"
                        onClick={handleReset}
                        icon={<RefreshCw className="w-4 h-4" />}
                      >
                        继续导入
                      </Button>
                    )}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
