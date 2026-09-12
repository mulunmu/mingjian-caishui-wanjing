import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import useChatStore from '@/stores/chatStore';
import CardGroup from '@/components/cards/CardGroup';
import DimensionCard from '@/components/cards/DimensionCard';
import FunctionCard from '@/components/cards/FunctionCard';
import ComboCard from '@/components/cards/ComboCard';
import ChatPanel from '@/components/chat/ChatPanel';
import { ResearchAssistantCharacter } from '@/components/ui/ResearchAssistantCharacter';
import { DimensionIcons, FunctionIcons, ComboIcons } from '@/components/ui/SketchIcons';
import { buildQueryText } from '@/utils/intentParser';
import { riskApi, type EnterpriseOption } from '@/api/risk';
import { Search, ChevronRight } from 'lucide-react';
import type { DimensionType, FunctionType, DimensionItem, FunctionItem, ComboItem } from '@/types/chat';

const dimensions: DimensionItem[] = [
  { id: 'overall', label: '整体', icon: 'overall', prefix: '分析整体' },
  { id: 'industry', label: '按行业', icon: 'industry', prefix: '分析各行业的' },
  { id: 'region', label: '按地区', icon: 'region', prefix: '分析各地区的' },
  { id: 'time', label: '按时间', icon: 'time', prefix: '分析各时间段的' },
  { id: 'signal', label: '按信号', icon: 'signal', prefix: '分析各信号的' },
];

const functions: FunctionItem[] = [
  { id: 'score', label: '评分', description: '六维风险评分', icon: 'score', suffix: '风险评分情况' },
  { id: 'authenticity', label: '真实性', description: '经营真实性验证', icon: 'authenticity', suffix: '经营真实性' },
  { id: 'fraud', label: '反欺诈', description: '进销错配检测', icon: 'fraud', suffix: '反欺诈分析' },
  { id: 'benchmark', label: '基准', description: '行业基准对比', icon: 'benchmark', suffix: '行业基准对比' },
  { id: 'trend', label: '趋势', description: '趋势走向分析', icon: 'trend', suffix: '趋势走向' },
];

const comboItems: ComboItem[] = [
  { id: 'c1', dimension: 'industry', function: 'trend', label: '行业×趋势', icon: 'industry+trend' },
  { id: 'c2', dimension: 'region', function: 'score', label: '地区×评分', icon: 'region+score' },
  { id: 'c3', dimension: 'industry', function: 'fraud', label: '行业×反欺诈', icon: 'industry+fraud' },
  { id: 'c4', dimension: 'time', function: 'trend', label: '时间×趋势', icon: 'time+trend' },
  { id: 'c5', dimension: 'overall', function: 'authenticity', label: '整体×真实性', icon: 'overall+authenticity' },
];

// 获取维度图标
function getDimensionIcon(iconName: string) {
  return DimensionIcons[iconName as keyof typeof DimensionIcons] || DimensionIcons.overall;
}

// 获取功能图标
function getFunctionIcon(iconName: string) {
  return FunctionIcons[iconName as keyof typeof FunctionIcons] || FunctionIcons.score;
}

// 获取组合图标
function getComboIcon(iconName: string) {
  return ComboIcons[iconName as keyof typeof ComboIcons] || ComboIcons['industry+trend'];
}

export default function ResearchCenter() {
  const navigate = useNavigate();
  const {
    context,
    selectDimension,
    selectFunction,
    sendMessage,
    isLoading,
  } = useChatStore();

  const [inputValue, setInputValue] = useState('');
  const [assistantState, setAssistantState] = useState<'idle' | 'typing' | 'answering'>('idle');

  // 单企业研判入口：搜索「企业N」→ 选中即跳企业风险披露页（复用 /enterprise/:id）
  const [enterpriseQuery, setEnterpriseQuery] = useState('');
  const [enterpriseOptions, setEnterpriseOptions] = useState<EnterpriseOption[]>([]);

  useEffect(() => {
    riskApi
      .getEnterprises()
      .then(setEnterpriseOptions)
      .catch(() => setEnterpriseOptions([]));
  }, []);

  useEffect(() => {
    if (!enterpriseQuery.trim()) return;
    const t = setTimeout(() => {
      riskApi
        .getEnterprises(enterpriseQuery)
        .then(setEnterpriseOptions)
        .catch(() => setEnterpriseOptions([]));
    }, 200);
    return () => clearTimeout(t);
  }, [enterpriseQuery]);

  // ?custom=1：来自报告中心/对话的「AI 定制报告」入口 → 自动发起定制对话
  const [searchParams, setSearchParams] = useSearchParams();
  const customParam = searchParams.get('custom');
  const customSentRef = useRef(false);
  useEffect(() => {
    if (customParam === '1') {
      if (!customSentRef.current && !isLoading) {
        customSentRef.current = true;
        sendMessage('我要定制一份风控报告');
        setSearchParams({}, { replace: true });
      }
    } else {
      customSentRef.current = false;
    }
  }, [customParam, isLoading, sendMessage, setSearchParams]);

  // 根据加载状态更新动画角色状态
  useEffect(() => {
    if (isLoading) {
      setAssistantState('answering');
    } else {
      const timer = setTimeout(() => {
        setAssistantState('idle');
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isLoading]);

  // 当用户输入时，角色进入打字状态
  const handleInputChange = useCallback((value: string) => {
    setInputValue(value);
    if (value.length > 0) {
      setAssistantState('typing');
    } else {
      setAssistantState('idle');
    }
  }, []);

  // 点击维度卡
  const handleDimensionClick = useCallback(
    (dim: DimensionType) => {
      selectDimension(dim);
      const query = buildQueryText(dim, context.currentFunction as FunctionType | null);
      setInputValue(query);
    },
    [context.currentFunction, selectDimension]
  );

  // 点击功能卡
  const handleFunctionClick = useCallback(
    (func: FunctionType) => {
      selectFunction(func);
      const query = buildQueryText(context.currentDimension as DimensionType | null, func);
      setInputValue(query);
    },
    [context.currentDimension, selectFunction]
  );

  // 点击组合卡：一键直达分析（组合已含维度+功能，直接发送，不再只填充输入框）
  const handleComboClick = useCallback(
    (combo: ComboItem) => {
      const dim = combo.dimension as DimensionType;
      const func = combo.function as FunctionType;
      selectDimension(dim);
      selectFunction(func);
      const query = buildQueryText(dim, func);
      setInputValue('');
      sendMessage(query);
    },
    [selectDimension, selectFunction, sendMessage]
  );

  // 发送消息
  const handleSend = useCallback(
    (text: string) => {
      setInputValue('');
      setAssistantState('answering');
      sendMessage(text);
    },
    [sendMessage]
  );

  // 单企业研判：选中某企业 → 跳转企业风险披露页
  const handleEnterpriseSelect = useCallback(
    (id: string) => {
      navigate(`/enterprise/${id}`);
    },
    [navigate]
  );

  return (
    <div className="flex h-full overflow-hidden">
      {/* 左侧：对话区 */}
      <div className="flex-1 flex flex-col min-w-0">
        <ChatPanel
          inputValue={inputValue}
          onInputChange={handleInputChange}
          onSend={handleSend}
          isLoading={isLoading}
        />
      </div>

      {/* 右侧面板：上半截独立滚动，底栏固定角色 */}
      <aside className="w-[300px] flex-shrink-0 border-l border-warm-200 bg-white flex flex-col h-full min-h-0 overflow-hidden">
        <div className="p-3 space-y-3 flex-1 min-h-0 overflow-y-auto">
          <div>
            <h2 className="text-base font-semibold text-warm-800 mb-1">风险评估</h2>
            <p className="text-xs text-warm-400">选择维度和功能，开始分析</p>
          </div>

          {/* 单企业研判入口：搜索「企业N」→ 跳企业风险披露 */}
          <CardGroup title="单企业研判">
            <div className="space-y-2">
              <div className="relative">
                <Search size={14} className="absolute left-2.5 top-2.5 text-warm-400" />
                <input
                  value={enterpriseQuery}
                  onChange={(e) => setEnterpriseQuery(e.target.value)}
                  placeholder="搜索「企业N」或行业/地区…"
                  className="w-full h-8 pl-8 pr-2 rounded-lg border border-warm-200 bg-warm-50 text-sm text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber"
                />
              </div>
              <div className="max-h-44 overflow-y-auto space-y-1">
                {enterpriseOptions.length === 0 ? (
                  <p className="text-xs text-warm-400 py-1">未匹配到企业</p>
                ) : (
                  enterpriseOptions.slice(0, 8).map((e) => (
                    <button
                      key={e.enterprise_id}
                      onClick={() => handleEnterpriseSelect(e.enterprise_id)}
                      className="w-full flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-amber-50 transition-colors"
                    >
                      <span className="text-[13px] text-warm-800 truncate">{e.display_name}</span>
                      <span className="text-[10px] text-warm-400 flex-shrink-0 truncate max-w-[110px]">
                        {e.industry_l1} · {e.province}
                      </span>
                      <ChevronRight size={12} className="text-warm-300 flex-shrink-0" />
                    </button>
                  ))
                )}
              </div>
            </div>
          </CardGroup>

          {/* 维度卡 */}
          <CardGroup title="分析维度">
            {dimensions.map((dim, i) => (
              <DimensionCard
                key={dim.id}
                item={dim}
                selected={context.currentDimension === dim.id}
                onClick={() => handleDimensionClick(dim.id)}
                index={i}
                icon={getDimensionIcon(dim.icon)}
              />
            ))}
          </CardGroup>

          {/* 功能卡 */}
          <CardGroup title="分析功能">
            {functions.map((func, i) => (
              <FunctionCard
                key={func.id}
                item={func}
                selected={context.currentFunction === func.id}
                onClick={() => handleFunctionClick(func.id)}
                index={i + 5}
                icon={getFunctionIcon(func.icon)}
              />
            ))}
          </CardGroup>

          {/* 组合卡 */}
          <CardGroup title="推荐组合">
            <div className="flex flex-wrap gap-2">
              {comboItems.map((combo, i) => (
                <ComboCard
                  key={combo.id}
                  item={combo}
                  onClick={() => handleComboClick(combo)}
                  index={i + 10}
                  icon={getComboIcon(combo.icon ?? '')}
                />
              ))}
            </div>
          </CardGroup>

          {/* 已覆盖功能 */}
          {context.coveredFunctions.length > 0 && (
            <div className="pt-2 border-t border-warm-100">
              <p className="text-xs text-warm-400 mb-1">已覆盖功能</p>
              <div className="flex flex-wrap gap-1">
                {context.coveredFunctions.map((f) => (
                  <span
                    key={f}
                    className="px-2 py-0.5 text-xs bg-sage/10 text-sage rounded-full"
                  >
                    {functions.find((fn) => fn.id === f)?.label || f}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 底栏固定：不随上半截滚动，首屏始终可见 */}
        <div className="flex-shrink-0 px-3 pb-2 pt-2 border-t border-warm-100 bg-white">
          <div className="flex items-end justify-center gap-3">
            {/* 主角色 */}
            <div className="flex flex-col items-center">
              <div className="overflow-hidden" style={{ height: '110px', width: '60px' }}>
                <div style={{ transform: 'scale(0.5)', transformOrigin: 'top left' }}>
                  <ResearchAssistantCharacter state={assistantState} variant="main" />
                </div>
              </div>
              <div className="text-center -mt-1">
                <span className="text-[10px] text-warm-400">
                  {assistantState === 'idle' && '待机中'}
                  {assistantState === 'typing' && '输入中'}
                  {assistantState === 'answering' && '分析中'}
                </span>
              </div>
            </div>
            {/* 副角色 */}
            <div className="flex flex-col items-end">
              <div className="overflow-hidden" style={{ height: '88px', width: '48px' }}>
                <div style={{ transform: 'scale(0.4)', transformOrigin: 'top left' }}>
                  <ResearchAssistantCharacter state={assistantState} variant="secondary" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
