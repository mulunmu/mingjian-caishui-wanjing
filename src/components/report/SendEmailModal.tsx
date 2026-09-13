import { useEffect, useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import Modal from '@/components/ui/Modal';
import useReportStore from '@/stores/reportStore';
import useAuthStore from '@/stores/authStore';

interface SendEmailModalProps {
  open: boolean;
  onClose: () => void;
  /** 要发送的报告（单份或批量） */
  reportIds: string[];
  titles?: string[];
}

/**
 * 报告发送弹窗（企划书阶段 C 场景 B）。
 *
 * 流程：收件人（预填注册邮箱）→ 受信直达；未受信 → 弹验证码输入 →
 * 发验证码 → 输码 → 校验（可勾选「记住」）→ 发送。
 */
export default function SendEmailModal({ open, onClose, reportIds, titles }: SendEmailModalProps) {
  const user = useAuthStore((s) => s.user);
  const { sendEmail, batchEmail } = useReportStore();
  const { sendCode, fetchFormToken } = useAuthStore();

  const [recipient, setRecipient] = useState('');
  const [code, setCode] = useState('');
  const [remember, setRemember] = useState(false);
  const [needVerify, setNeedVerify] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [formToken, setFormToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isBatch = reportIds.length > 1;

  useEffect(() => {
    if (open) {
      setRecipient(user?.email || '');
      setCode('');
      setRemember(false);
      setNeedVerify(false);
      setMessage(null);
      setError(null);
    }
  }, [open, user?.email]);

  useEffect(() => {
    if (open) void fetchFormToken().then(setFormToken);
  }, [open, fetchFormToken]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(recipient.trim());

  const handleSendCode = async () => {
    setError(null);
    if (!validEmail) {
      setError('请填写正确的收件邮箱');
      return;
    }
    setSendingCode(true);
    const res = await sendCode(recipient.trim(), 'send_email', formToken);
    setSendingCode(false);
    if (!res.ok) {
      setError(res.message);
      void fetchFormToken().then(setFormToken);
      return;
    }
    setCountdown(res.resendAfter ?? 60);
  };

  const doSend = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const payload = { recipient: recipient.trim(), code: code.trim() || undefined, remember };
    const res = isBatch
      ? await batchEmail({ report_ids: reportIds, ...payload })
      : await sendEmail({ report_id: reportIds[0], ...payload });
    setBusy(false);

    if (res.ok) {
      setMessage(res.message);
      // 发送成功后短暂停留再关闭，让用户看到回执
      setTimeout(onClose, 900);
      return;
    }
    if (res.needVerify) {
      setNeedVerify(true);
      return;
    }
    setError(res.message);
  };

  return (
    <Modal open={open} onClose={onClose} title={isBatch ? '批量发送报告' : '发送报告'}>
      <div className="space-y-4">
        {isBatch && (
          <p className="text-xs text-warm-500">
            将 {reportIds.length} 份报告发送到同一收件人：
          </p>
        )}

        {/* 收件人 */}
        <div className="space-y-1.5">
          <label className="text-sm font-medium text-warm-700">收件邮箱</label>
          <input
            type="email"
            placeholder="recipient@example.com"
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
            className="h-11 w-full rounded-lg border border-warm-200 bg-white px-3 py-2 text-sm text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
          />
          <p className="text-[11px] text-warm-400">
            注册邮箱 / 已验证邮箱直接发送；其他邮箱需验证码。
          </p>
        </div>

        {/* 验证码区（未受信时展开） */}
        {needVerify && (
          <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50/50 p-3">
            <p className="text-xs text-warm-600">该邮箱尚未受信，请输入验证码后发送：</p>
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="6 位验证码"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                className="h-10 flex-1 min-w-0 rounded-lg border border-warm-200 bg-white px-3 py-2 text-sm text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
              />
              <button
                type="button"
                onClick={handleSendCode}
                disabled={countdown > 0 || sendingCode}
                className="h-10 shrink-0 rounded-lg border border-warm-200 bg-white px-3 text-xs font-medium text-warm-700 hover:border-amber hover:text-amber disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
              >
                {countdown > 0 ? `${countdown}s 后重发` : sendingCode ? '发送中...' : '发送验证码'}
              </button>
            </div>
            <label className="flex items-center gap-2 text-xs text-warm-600 cursor-pointer">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="accent-amber"
              />
              记住该邮箱为受信邮箱（下次直达）
            </label>
          </div>
        )}

        {message && (
          <div className="p-2.5 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg">
            {message}
          </div>
        )}
        {error && (
          <div className="p-2.5 text-sm text-terracotta bg-terracotta/10 border border-terracotta/30 rounded-lg">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="h-9 px-4 rounded-lg border border-warm-200 text-sm text-warm-600 hover:bg-warm-50 transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={doSend}
            disabled={busy || !validEmail || (needVerify && !code.trim())}
            className="flex items-center gap-1.5 h-9 px-4 rounded-lg bg-amber text-white text-sm font-medium hover:bg-amber-dark disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            {busy ? '发送中...' : needVerify ? '确认发送' : '发送'}
          </button>
        </div>
      </div>
    </Modal>
  );
}
