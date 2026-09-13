import { useEffect, useState } from 'react';
import { RefreshCw, Loader2, Mail, AlertTriangle, RotateCcw } from 'lucide-react';
import { emailApi } from '@/api/email';
import type { EmailLogItem } from '@/types/email';

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  sent: { text: '已发送', cls: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  failed: { text: '失败', cls: 'text-terracotta bg-terracotta/10 border-terracotta/30' },
  pending: { text: '发送中', cls: 'text-amber-700 bg-amber-50 border-amber-200' },
};

/** 发送记录页（全程审计）：展示 EmailLog，失败的报告邮件可重发。 */
export default function EmailLogsPage() {
  const [logs, setLogs] = useState<EmailLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState('');
  const [resendingId, setResendingId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await emailApi.logs({ status: status || undefined, limit: 100 });
      setLogs(res.items || []);
      setTotal(res.total || 0);
    } catch {
      setError('发送记录加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const handleResend = async (log: EmailLogItem) => {
    setResendingId(log.id);
    setNotice(null);
    try {
      const res = await emailApi.resend(log.id);
      setNotice(res.message);
    } catch {
      setNotice('重发失败，请稍后重试');
    } finally {
      setResendingId(null);
      void fetchLogs();
    }
  };

  return (
    <div className="h-full flex flex-col bg-warm-50">
      <div className="bg-white border-b border-warm-200 px-6 py-3 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-warm-800">发送记录</h1>
          <p className="text-xs text-warm-400 mt-0.5">邮件交付全程审计（验证码 + 报告）</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-8 px-2 rounded-lg border border-warm-200 bg-white text-xs text-warm-600 focus:outline-none focus:border-amber"
          >
            <option value="">全部状态</option>
            <option value="sent">已发送</option>
            <option value="failed">失败</option>
            <option value="pending">发送中</option>
          </select>
          <button
            onClick={fetchLogs}
            disabled={loading}
            className="flex items-center gap-1.5 h-8 px-3 rounded-lg border border-warm-200 text-xs text-warm-600 hover:bg-warm-100 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {notice && (
        <div className="bg-emerald-50 border-b border-emerald-200 px-6 py-2 text-xs text-emerald-700">
          {notice}
        </div>
      )}

      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-5 h-5 text-warm-400 animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
            <AlertTriangle className="w-8 h-8 text-terracotta mb-3" />
            <p className="text-sm text-warm-700">{error}</p>
            <button
              onClick={fetchLogs}
              className="mt-3 h-8 px-3 rounded-lg border border-warm-200 text-xs text-warm-600 hover:bg-warm-50"
            >
              重试
            </button>
          </div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
            <Mail className="w-10 h-10 text-warm-300 mb-2" />
            <p className="text-warm-400 text-sm">暂无发送记录</p>
            <p className="text-warm-300 text-xs mt-1">共 {total} 条记录</p>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto p-6 space-y-2">
            <p className="text-xs text-warm-400 mb-1">共 {total} 条记录</p>
            {logs.map((log) => {
              const st = STATUS_LABEL[log.status] || STATUS_LABEL.pending;
              return (
                <div
                  key={log.id}
                  className="rounded-lg border border-warm-200 bg-white p-3 flex items-start gap-3"
                >
                  <div className="w-8 h-8 rounded bg-warm-100 flex items-center justify-center flex-shrink-0">
                    <Mail className="w-4 h-4 text-warm-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-warm-800 font-medium truncate">
                        {log.recipient}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${st.cls}`}>
                        {st.text}
                      </span>
                      <span className="text-[10px] text-warm-400">
                        {log.kind === 'verify_code' ? '验证码' : '报告'}
                      </span>
                    </div>
                    {log.subject && (
                      <p className="text-xs text-warm-500 mt-0.5 truncate">{log.subject}</p>
                    )}
                    {log.error && (
                      <p className="text-[11px] text-terracotta mt-0.5 truncate">{log.error}</p>
                    )}
                    <p className="text-[11px] text-warm-400 mt-0.5">{fmtTime(log.created_at)}</p>
                  </div>
                  {log.kind === 'report' && log.status === 'failed' && log.report_id && (
                    <button
                      onClick={() => handleResend(log)}
                      disabled={resendingId === log.id}
                      className="flex items-center gap-1 h-7 px-2.5 rounded-lg border border-warm-200 text-xs text-warm-600 hover:bg-warm-50 disabled:opacity-50 flex-shrink-0 transition-colors"
                    >
                      <RotateCcw className="w-3 h-3" />
                      重发
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
