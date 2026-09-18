import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowDown,
  ArrowUp,
  Check,
  FilePlus2,
  Layers3,
  Loader2,
  MessageSquare,
  Plus,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { reportApi } from '@/api/report';
import { riskApi, type EnterpriseOption, type IndustryItem } from '@/api/risk';
import type { CustomReportCatalog, CustomReportSpec } from '@/types/report';

type ScopeType = 'all' | 'industry' | 'enterprise';

function buildSpec(params: {
  chapters: string[];
  scopeType: ScopeType;
  industryL1: string | null;
  enterpriseId: string | null;
  title: string;
  purpose: string;
  chapterAnalyses: Record<string, string[]>;
}): CustomReportSpec {
  return {
    chapters: params.chapters,
    industry_l1: params.scopeType === 'industry' ? params.industryL1 : null,
    enterprises: params.scopeType === 'enterprise' && params.enterpriseId ? [params.enterpriseId] : [],
    title: params.title.trim() || '定制风控报告',
    purpose: params.purpose.trim(),
    chapter_analyses: params.chapterAnalyses,
  };
}

export default function CustomReportPage() {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState<CustomReportCatalog | null>(null);
  const [industries, setIndustries] = useState<IndustryItem[]>([]);
  const [enterprises, setEnterprises] = useState<EnterpriseOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [scopeType, setScopeType] = useState<ScopeType>('all');
  const [industryL1, setIndustryL1] = useState<string | null>(null);
  const [enterpriseId, setEnterpriseId] = useState<string | null>(null);
  const [enterpriseQuery, setEnterpriseQuery] = useState('');
  const [title, setTitle] = useState('定制风控报告');
  const [chapterAnalyses, setChapterAnalyses] = useState<Record<string, string[]>>({});
  const [activeModule, setActiveModule] = useState<string | null>(null);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [planning, setPlanning] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ report_id: string; title: string } | null>(null);

  useEffect(() => {
    setLoadingCatalog(true);
    Promise.all([reportApi.customCatalog(), riskApi.getIndustries(), riskApi.getEnterprises(undefined, 30)])
      .then(([nextCatalog, nextIndustries, nextEnterprises]) => {
        setCatalog(nextCatalog);
        setIndustries(nextIndustries);
        setEnterprises(nextEnterprises);
      })
      .catch(() => setError('定制报告目录加载失败，请稍后重试。'))
      .finally(() => setLoadingCatalog(false));
  }, []);

  useEffect(() => {
    if (scopeType !== 'enterprise') return;
    const timer = setTimeout(() => {
      riskApi
        .getEnterprises(enterpriseQuery || undefined, 30)
        .then(setEnterprises)
        .catch(() => setEnterprises([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [enterpriseQuery, scopeType]);

  const available = useMemo(
    () => (catalog?.chapters || []).filter((chapter) => !selected.includes(chapter.key)),
    [catalog, selected]
  );

  const selectedChapters = useMemo(
    () => selected.map((key) => catalog?.chapters.find((chapter) => chapter.key === key)).filter(Boolean),
    [catalog, selected]
  );

  const availableGroups = useMemo(() => {
    const groups = new Map<string, typeof available>();
    available.forEach((chapter) => {
      const current = groups.get(chapter.category) || [];
      current.push(chapter);
      groups.set(chapter.category, current);
    });
    return Array.from(groups.entries());
  }, [available]);

  const derivedPurpose = useMemo(() => {
    const titles = selectedChapters.map((chapter) => chapter?.title).filter(Boolean);
    if (!titles.length) return '回答所选模块共同揭示的风险与处置重点。';
    return `回答「${titles.join('、')}」之间的经营风险、异常线索与处置优先级。`;
  }, [selectedChapters]);

  const spec = useMemo(
    () => buildSpec({ chapters: selected, scopeType, industryL1, enterpriseId, title, purpose: derivedPurpose, chapterAnalyses }),
    [selected, scopeType, industryL1, enterpriseId, title, derivedPurpose, chapterAnalyses]
  );

  const scopeReady =
    scopeType === 'all' ||
    (scopeType === 'industry' && Boolean(industryL1)) ||
    (scopeType === 'enterprise' && Boolean(enterpriseId));

  useEffect(() => {
    if (!selected.length || !scopeReady) return;
    setPlanning(true);
    const timer = setTimeout(() => {
      reportApi
        .planCustom(spec)
        .catch(() => null)
        .finally(() => setPlanning(false));
    }, 220);
    return () => clearTimeout(timer);
  }, [spec, selected.length, scopeReady]);

  const addChapter = (key: string) => {
    setSelected((current) => [...current, key]);
    setActiveModule(key);
    setError(null);
    setResult(null);
  };

  const removeChapter = (key: string) => {
    setSelected((current) => current.filter((item) => item !== key));
    setChapterAnalyses((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setActiveModule((current) => (current === key ? null : current));
    setError(null);
    setResult(null);
  };

  const moveChapter = (index: number, direction: -1 | 1) => {
    setSelected((current) => {
      const next = [...current];
      const target = index + direction;
      if (target < 0 || target >= next.length) return next;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const toggleAnalysis = (moduleKey: string, patternKey: string) => {
    setChapterAnalyses((current) => {
      const values = current[moduleKey] || [];
      const nextValues = values.includes(patternKey)
        ? values.filter((item) => item !== patternKey)
        : [...values, patternKey];
      return { ...current, [moduleKey]: nextValues };
    });
  };

  const generate = async () => {
    if (!selected.length || !scopeReady) {
      setError('请先按顺序添加至少一个章节，并确定分析范围。');
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const plan = await reportApi.planCustom(spec);
      const response = await reportApi.generateCustom(plan.spec);
      setResult({ report_id: response.report_id, title: response.title || title });
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || '报告生成失败，请检查所选章节与数据范围后重试。');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="h-full overflow-hidden bg-warm-50">
      <div className="mx-auto flex h-full max-w-[1320px] flex-col px-5 py-4">
        <div className="mb-4 flex flex-shrink-0 items-start justify-between gap-4">
          <div>
            <button type="button" onClick={() => navigate('/report')} className="mb-3 inline-flex items-center gap-1 text-xs text-warm-500 hover:text-warm-800">
              <ArrowLeft size={13} /> 返回报告中心
            </button>
            <h1 className="text-xl font-semibold text-warm-900">定制报告工作台</h1>
            <p className="mt-1 text-sm text-warm-500">逐个添加章节，调整顺序与范围；系统只组合已注册且可执行的指标模块。</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/research', { state: { startCustomReport: true } })}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 text-xs text-amber-800 hover:bg-amber-50"
            >
              <MessageSquare size={13} /> 对话式定制
            </button>
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">当前方案：{selected.length} 个章节</div>
          </div>
        </div>

        {loadingCatalog ? (
          <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-warm-500"><Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在加载章节与指标目录</div>
        ) : (
          <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto xl:grid-cols-[260px_minmax(0,1fr)_320px] xl:overflow-hidden">
            <aside className="min-h-0 rounded-xl border border-warm-200 bg-white p-4 xl:overflow-y-auto xl:pr-3">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-warm-800"><Layers3 size={15} className="text-amber-600" /> 可选模块</div>
              <div className="space-y-4">
                {availableGroups.map(([category, chapters]) => (
                  <div key={category}>
                    <p className="mb-1.5 text-[11px] font-medium text-warm-500">{category}</p>
                    <div className="space-y-2">
                      {chapters.map((chapter) => (
                        <button key={chapter.key} type="button" onClick={() => addChapter(chapter.key)} className="w-full rounded-lg border border-warm-200 px-3 py-2 text-left transition hover:border-amber-300 hover:bg-amber-50">
                          <div className="flex items-center justify-between gap-2"><span className="text-xs font-medium text-warm-800">{chapter.title}</span><Plus size={13} className="text-amber-600" /></div>
                          <p className="mt-1 text-[11px] leading-4 text-warm-400">{chapter.description}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                {!available.length && <p className="text-xs text-warm-400">所有可执行模块都已加入。</p>}
              </div>
            </aside>

            <main className="min-h-0 space-y-4 xl:overflow-y-auto xl:pr-1">
              <section className="rounded-xl border border-warm-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm font-medium text-warm-800"><FilePlus2 size={15} className="text-amber-600" /> 章节顺序</div>
                  {planning && <span className="text-[11px] text-warm-400">正在校验组合…</span>}
                </div>
                {!selectedChapters.length ? (
                  <div className="rounded-lg border border-dashed border-warm-200 px-4 py-10 text-center text-sm text-warm-400">从左侧逐个添加章节。先加一个模块，再决定下一个，不会一次性替你拼完整报告。</div>
                ) : (
                  <div className="space-y-2">
                    {selectedChapters.map((chapter, index) => (
                      <div
                        key={chapter!.key}
                        role="button"
                        tabIndex={0}
                        onClick={() => setActiveModule(chapter!.key)}
                        onKeyDown={(event) => { if (event.key === 'Enter') setActiveModule(chapter!.key); }}
                        className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-3 ${activeModule === chapter!.key ? 'border-amber-400 bg-amber-50/60' : 'border-warm-200 bg-warm-50/60'}`}
                      >
                        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-xs font-medium text-amber-800">{index + 1}</span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-warm-800">{chapter!.title}</p>
                          <p className="truncate text-[11px] text-warm-400">{chapter!.description}</p>
                          {(chapterAnalyses[chapter!.key] || []).length > 0 && (
                            <p className="mt-1 text-[10px] text-amber-700">分析方式：{(chapterAnalyses[chapter!.key] || []).map((key) => catalog?.analysis_patterns.find((item) => item.key === key)?.label || key).join('、')}</p>
                          )}
                        </div>
                        <button type="button" onClick={(event) => { event.stopPropagation(); moveChapter(index, -1); }} disabled={index === 0} className="rounded p-1 text-warm-400 hover:bg-white disabled:opacity-30" title="上移"><ArrowUp size={14} /></button>
                        <button type="button" onClick={(event) => { event.stopPropagation(); moveChapter(index, 1); }} disabled={index === selectedChapters.length - 1} className="rounded p-1 text-warm-400 hover:bg-white disabled:opacity-30" title="下移"><ArrowDown size={14} /></button>
                        <button type="button" onClick={(event) => { event.stopPropagation(); removeChapter(chapter!.key); }} className="rounded p-1 text-warm-400 hover:bg-white hover:text-red-500" title="移除"><Trash2 size={14} /></button>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {activeModule && catalog?.analysis_patterns?.length ? (
                <section className="rounded-xl border border-warm-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-warm-800">模块分析方式</p>
                      <p className="mt-0.5 text-[11px] text-warm-400">
                        当前作用于「{selectedChapters.find((item) => item?.key === activeModule)?.title || activeModule}」，可多选。
                      </p>
                    </div>
                    <button type="button" onClick={() => setActiveModule(null)} className="text-[11px] text-warm-400 hover:text-warm-700">收起</button>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {catalog.analysis_patterns
                      .filter((pattern) => !['report', 'overview', 'metric_lookup'].includes(pattern.key))
                      .map((pattern) => {
                        const checked = (chapterAnalyses[activeModule] || []).includes(pattern.key);
                        return (
                          <button
                            key={pattern.key}
                            type="button"
                            onClick={() => toggleAnalysis(activeModule, pattern.key)}
                            className={`rounded-full border px-3 py-1.5 text-xs transition ${checked ? 'border-amber-400 bg-amber-50 text-amber-800' : 'border-warm-200 text-warm-500 hover:border-amber-300'}`}
                          >
                            {pattern.label}
                          </button>
                        );
                      })}
                  </div>
                </section>
              ) : null}

              <section className="rounded-xl border border-warm-200 bg-white p-4">
                <label className="mb-1.5 block text-xs font-medium text-warm-600">报告标题</label>
                <input value={title} onChange={(event) => setTitle(event.target.value)} className="h-9 w-full rounded-lg border border-warm-200 px-3 text-sm text-warm-800 outline-none focus:border-amber-400" />
                <div className="mt-3 rounded-lg border border-warm-100 bg-warm-50 px-3 py-2">
                  <p className="text-[10px] font-medium text-warm-500">系统自动生成的问题</p>
                  <p className="mt-1 text-xs leading-5 text-warm-700">{derivedPurpose}</p>
                </div>
              </section>
            </main>

            <aside className="min-h-0 space-y-4 xl:overflow-y-auto xl:pr-1">
              <section className="rounded-xl border border-warm-200 bg-white p-4">
                <p className="mb-3 text-sm font-medium text-warm-800">分析范围</p>
                <div className="grid grid-cols-3 gap-1.5">
                  {([['all', '全库'], ['industry', '行业'], ['enterprise', '企业']] as const).map(([key, label]) => (
                    <button key={key} type="button" onClick={() => setScopeType(key)} className={`rounded-lg border px-2 py-1.5 text-xs ${scopeType === key ? 'border-amber-400 bg-amber-50 text-amber-800' : 'border-warm-200 text-warm-500'}`}>{label}</button>
                  ))}
                </div>
                {scopeType === 'industry' && (
                  <select value={industryL1 || ''} onChange={(event) => setIndustryL1(event.target.value || null)} className="mt-3 h-9 w-full rounded-lg border border-warm-200 bg-white px-2 text-sm text-warm-700">
                    <option value="">选择行业</option>
                    {industries.map((item) => <option key={item.industry_l1} value={item.industry_l1}>{item.industry_l1}（{item.n}）</option>)}
                  </select>
                )}
                {scopeType === 'enterprise' && (
                  <div className="mt-3">
                    <input value={enterpriseQuery} onChange={(event) => setEnterpriseQuery(event.target.value)} placeholder="搜索企业…" className="h-9 w-full rounded-lg border border-warm-200 px-3 text-sm outline-none focus:border-amber-400" />
                    <div className="mt-2 max-h-40 space-y-1 overflow-y-auto">
                      {enterprises.map((item) => (
                        <button key={item.enterprise_id} type="button" onClick={() => setEnterpriseId(item.enterprise_id)} className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-xs ${enterpriseId === item.enterprise_id ? 'bg-amber-50 text-amber-800' : 'hover:bg-warm-50 text-warm-600'}`}><span className="truncate">{item.display_name}</span>{enterpriseId === item.enterprise_id && <Check size={12} />}</button>
                      ))}
                    </div>
                  </div>
                )}
              </section>

              <section className="rounded-xl border border-warm-200 bg-white p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-warm-800"><Sparkles size={15} className="text-amber-600" /> 生成预览</div>
                <p className="mt-2 text-xs leading-5 text-warm-500">{selected.length ? `将按 ${selected.length} 个章节顺序组装，每个章节只引用对应指标与 Claim。` : '添加章节后，这里会显示组装顺序。'}</p>
                <button type="button" onClick={generate} disabled={generating || !selected.length || !scopeReady} className="mt-4 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-amber-500 text-sm font-medium text-white transition hover:bg-amber-600 disabled:opacity-40">{generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}{generating ? '生成中…' : '生成定制报告'}</button>
                {result && <button type="button" onClick={() => navigate(`/report/${result.report_id}`)} className="mt-2 inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg border border-amber-300 text-sm text-amber-800 hover:bg-amber-50"><Check size={14} /> 查看《{result.title}》</button>}
                {error && <p className="mt-3 text-xs leading-5 text-red-500">{error}</p>}
              </section>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
