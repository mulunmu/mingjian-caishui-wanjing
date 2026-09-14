import { useState, useCallback, useEffect, useRef, memo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import useChatStore from '@/stores/chatStore';
import ChatPanel from '@/components/chat/ChatPanel';
import { ResearchAssistantCharacter } from '@/components/ui/ResearchAssistantCharacter';
import { riskApi, type EnterpriseOption } from '@/api/risk';
import Modal from '@/components/ui/Modal';
import DataIngestPage from '@/pages/DataIngestPage';
import { Search, ChevronRight, Upload } from 'lucide-react';
import type { FollowUpItem } from '@/types/chat';

/** 吉祥物隔离：mousemove 状态不驱动整页重渲染 */
const AssistantDock = memo(function AssistantDock({
  state,
}: {
  state: 'idle' | 'typing' | 'answering';
}) {
  return (
    <div className="flex-shrink-0 px-3 pb-2 pt-2 border-t border-warm-100 bg-white">
      <div className="flex items-end justify-center gap-3">
        <div className="flex flex-col items-center">
          <div className="overflow-hidden" style={{ height: '110px', width: '60px' }}>
            <div style={{ transform: 'scale(0.5)', transformOrigin: 'top left' }}>
              <ResearchAssistantCharacter state={state} variant="main" />
            </div>
          </div>
          <span className="text-[10px] text-warm-400 -mt-1">
            {state === 'idle' && '待机中'}
            {state === 'typing' && '输入中'}
            {state === 'answering' && '分析中'}
          </span>
        </div>
      </div>
    </div>
  );
});

export default function ResearchCenter() {
  const navigate = useNavigate();
  const {
    sendMessage,
    isLoading,
    clickFollowUp,
    setEnterpriseId,
    enterpriseId,
    dialogueState,
    ui,
    bootstrapSession,
  } = useChatStore();
  const ingestModalOpen = useChatStore((s) => s.ingestModalOpen);
  const closeIngestModal = useChatStore((s) => s.closeIngestModal);
  const openIngestModal = useChatStore((s) => s.openIngestModal);

  const [inputValue, setInputValue] = useState('');
  const [assistantState, setAssistantState] = useState<'idle' | 'typing' | 'answering'>('idle');
  const [enterpriseQuery, setEnterpriseQuery] = useState('');
  const [enterpriseOptions, setEnterpriseOptions] = useState<EnterpriseOption[]>([]);
  const [showAllEnterprises, setShowAllEnterprises] = useState(false);
  const [pickerHighlight, setPickerHighlight] = useState(false);
  const bootRef = useRef(false);

  // 首屏 bootstrap：从后端拉 scope UI（不静默绑企业）
  useEffect(() => {
    if (bootRef.current) return;
    bootRef.current = true;
    void bootstrapSession();
  }, [bootstrapSession]);

  useEffect(() => {
    riskApi
      .getEnterprises(undefined, showAllEnterprises ? 80 : 12)
      .then(setEnterpriseOptions)
      .catch(() => setEnterpriseOptions([]));
  }, [showAllEnterprises]);

  useEffect(() => {
    if (!enterpriseQuery.trim()) return;
    const t = setTimeout(() => {
      riskApi
        .getEnterprises(enterpriseQuery, 40)
        .then(setEnterpriseOptions)
        .catch(() => setEnterpriseOptions([]));
    }, 200);
    return () => clearTimeout(t);
  }, [enterpriseQuery]);

  const [searchParams, setSearchParams] = useSearchParams();
  const customParam = searchParams.get('custom');
  const ingestParam = searchParams.get('ingest');
  const customSentRef = useRef(false);

  useEffect(() => {
    if (ingestParam === '1') {
      openIngestModal();
      setSearchParams({}, { replace: true });
    }
  }, [ingestParam, openIngestModal, setSearchParams]);

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

  useEffect(() => {
    if (isLoading) {
      setAssistantState('answering');
    } else {
      const timer = setTimeout(() => setAssistantState('idle'), 500);
      return () => clearTimeout(timer);
    }
  }, [isLoading]);

  const handleInputChange = useCallback((value: string) => {
    setInputValue(value);
    setAssistantState(value ? 'typing' : 'idle');
  }, []);

  const handleSend = useCallback(
    (text: string) => {
      setInputValue('');
      setAssistantState('answering');
      void sendMessage(text);
    },
    [sendMessage]
  );

  const handleEnterpriseSelect = useCallback(
    (id: string, name?: string) => {
      setEnterpriseId(id);
      setPickerHighlight(false);
      const item: FollowUpItem = {
        type: 'switch_scope',
        label: `分析「${name || '选定企业'}」`,
        target: 'individual',
        params: { enterprise_id: id, display_name: name || '选定企业' },
      };
      clickFollowUp(item);
    },
    [setEnterpriseId, clickFollowUp]
  );

  const scope = dialogueState?.scope || 'unbound';
  const scopeBar = ui?.scope_bar;
  const scenarioButtons = ui?.scenario_buttons || [];

  const onScenarioClick = (btn: {
    id: string;
    question?: string;
    action?: string;
  }) => {
    if (btn.action === 'use_demo') {
      clickFollowUp({
        type: 'switch_scope',
        label: '试用演示企业',
        target: 'individual',
        params: { use_demo: true },
      });
      return;
    }
    if (btn.action === 'open_picker') {
      setPickerHighlight(true);
      return;
    }
    if (btn.action === 'use_cohort') {
      clickFollowUp({
        type: 'switch_scope',
        label: '看全库 193 家群体',
        target: 'cohort',
      });
      return;
    }
    if (btn.action === 'ingest') {
      openIngestModal();
      return;
    }
    if (btn.question === '生成报告') {
      navigate('/report?wizard=1');
      return;
    }
    if (btn.question) clickFollowUp(btn.question);
  };

  return (
    <div className="flex h-full overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0">
        <ChatPanel
          inputValue={inputValue}
          onInputChange={handleInputChange}
          onSend={handleSend}
          isLoading={isLoading}
        />
      </div>

      <aside className="w-[300px] flex-shrink-0 border-l border-warm-200 bg-white flex flex-col h-full min-h-0 overflow-hidden">
        <div className="p-3 space-y-3 flex-1 min-h-0 overflow-y-auto">
          <div>
            <h2 className="text-base font-semibold text-warm-800 mb-1">风险研判</h2>
            <p className="text-xs text-warm-400">先选范围，再顺着问</p>
          </div>

          {/* 当前范围条（R5） */}
          <div className="rounded-lg border border-warm-200 bg-warm-50 px-3 py-2">
            <p className="text-[11px] text-warm-400 mb-0.5">当前范围</p>
            <p className="text-[13px] font-medium text-warm-800">
              {scopeBar?.label || '尚未选择范围'}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {scope !== 'individual' && (
                <button
                  type="button"
                  className="text-[11px] px-2 py-1 rounded border border-amber/30 text-amber hover:bg-amber/5"
                  onClick={() =>
                    clickFollowUp({
                      type: 'switch_scope',
                      label: '试用演示企业',
                      target: 'individual',
                      params: { use_demo: true },
                    })
                  }
                >
                  试用演示
                </button>
              )}
              {scope === 'individual' && (
                <button
                  type="button"
                  className="text-[11px] px-2 py-1 rounded border border-warm-300 text-warm-600 hover:bg-warm-100"
                  onClick={() =>
                    clickFollowUp({
                      type: 'switch_scope',
                      label: '看全库 193 家群体',
                      target: 'cohort',
                    })
                  }
                >
                  看全库
                </button>
              )}
              {scope === 'cohort' && (
                <button
                  type="button"
                  className="text-[11px] px-2 py-1 rounded border border-warm-300 text-warm-600 hover:bg-warm-100"
                  onClick={() =>
                    clickFollowUp({
                      type: 'switch_scope',
                      label: '重新选范围',
                      target: 'unbound',
                    })
                  }
                >
                  重选范围
                </button>
              )}
              <button
                type="button"
                onClick={openIngestModal}
                className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded border border-warm-300 text-warm-600 hover:bg-warm-100"
              >
                <Upload size={11} />
                数据接入
              </button>
            </div>
          </div>

          {/* 场景按钮：完全由后端 state 派生 */}
          <div>
            <p className="text-[11px] text-warm-400 mb-2">
              {scope === 'unbound' ? '先选入口' : scope === 'cohort' ? '群体追问' : '按场景继续问'}
            </p>
            <div className="grid grid-cols-2 gap-2">
              {scenarioButtons.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  disabled={isLoading}
                  onClick={() => onScenarioClick(s)}
                  className="text-left rounded-lg border border-warm-200 bg-warm-50 px-2.5 py-2 hover:border-amber/40 hover:bg-amber/5 transition-colors disabled:opacity-50"
                >
                  <div className="text-[12px] font-medium text-warm-800">{s.label}</div>
                  <div className="text-[10px] text-warm-400 mt-0.5">{s.hint}</div>
                </button>
              ))}
            </div>
          </div>

          <div
            className={`pt-2 border-t border-warm-100 ${
              pickerHighlight ? 'ring-2 ring-amber/40 rounded-lg p-2 -mx-1' : ''
            }`}
          >
            <p className="text-[11px] text-warm-400 mb-1.5">
              {pickerHighlight ? '请点选一家企业' : '换一家 / 选企业'}
            </p>
            <div className="relative mb-2">
              <Search size={14} className="absolute left-2.5 top-2.5 text-warm-400" />
              <input
                value={enterpriseQuery}
                onChange={(e) => setEnterpriseQuery(e.target.value)}
                placeholder="搜索「企业N」…"
                className="w-full h-8 pl-8 pr-2 rounded-lg border border-warm-200 bg-warm-50 text-sm text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber"
              />
            </div>
            <div className="max-h-44 overflow-y-auto space-y-1">
              {(showAllEnterprises ? enterpriseOptions : enterpriseOptions.slice(0, 6)).map((e) => (
                <button
                  key={e.enterprise_id}
                  type="button"
                  onClick={() => handleEnterpriseSelect(e.enterprise_id, e.display_name)}
                  className={`w-full flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left transition-colors ${
                    enterpriseId === e.enterprise_id
                      ? 'bg-amber/10 border border-amber/30'
                      : 'hover:bg-amber-50'
                  }`}
                >
                  <span className="text-[12px] text-warm-800 truncate">{e.display_name}</span>
                  <ChevronRight size={12} className="text-warm-300 flex-shrink-0" />
                </button>
              ))}
            </div>
            {enterpriseOptions.length > 6 && (
              <button
                type="button"
                onClick={() => setShowAllEnterprises((v) => !v)}
                className="mt-1.5 text-[11px] text-amber hover:text-amber-dark"
              >
                {showAllEnterprises ? '收起' : `查看更多（最多 ${enterpriseOptions.length}）`}
              </button>
            )}
          </div>
        </div>

        <AssistantDock state={assistantState} />
      </aside>

      <Modal
        open={ingestModalOpen}
        onClose={closeIngestModal}
        title="数据接入"
        widthClass="w-[920px] max-w-[96vw]"
      >
        <div className="max-h-[75vh] overflow-y-auto -mx-2 px-2">
          <DataIngestPage />
        </div>
      </Modal>
    </div>
  );
}
