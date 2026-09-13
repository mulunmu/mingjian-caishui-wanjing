import { useEffect, useState } from 'react';
import { ShieldCheck, Plus, Trash2, Loader2, RefreshCw } from 'lucide-react';
import useAuthStore from '@/stores/authStore';
import { emailApi } from '@/api/email';
import type { TrustedEmailItem } from '@/types/email';

function sourceLabel(source: string): string {
  return source === 'register' ? '注册邮箱' : '已验证';
}

/** 账号页：用户信息 + 受信邮箱管理（可增删）。 */
export default function AccountPage() {
  const { user, sendCode, verifyCode, fetchFormToken } = useAuthStore();
  const [trusted, setTrusted] = useState<TrustedEmailItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [newEmail, setNewEmail] = useState('');
  const [code, setCode] = useState('');
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [formToken, setFormToken] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const fetchTrusted = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await emailApi.listTrusted();
      setTrusted(res.items || []);
    } catch {
      setError('受信邮箱加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchTrusted();
    void fetchFormToken().then(setFormToken);
  }, [fetchFormToken]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newEmail.trim());

  const handleSendCode = async () => {
    setError(null);
    setNotice(null);
    if (!validEmail) {
      setError('请填写正确的邮箱地址');
      return;
    }
    setSendingCode(true);
    const res = await sendCode(newEmail.trim(), 'bind_email', formToken);
    setSendingCode(false);
    if (!res.ok) {
      setError(res.message);
      void fetchFormToken().then(setFormToken);
      return;
    }
    setCountdown(res.resendAfter ?? 60);
  };

  const handleVerify = async () => {
    setError(null);
    setNotice(null);
    if (!validEmail || !code.trim()) {
      setError('请填写邮箱和验证码');
      return;
    }
    const res = await verifyCode(newEmail.trim(), 'bind_email', code.trim());
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setNotice('已添加受信邮箱');
    setNewEmail('');
    setCode('');
    setCountdown(0);
    void fetchTrusted();
  };

  const handleRemove = async (email: string) => {
    setRemoving(email);
    setNotice(null);
    try {
      await emailApi.removeTrusted(email);
      setTrusted((list) => list.filter((t) => t.email !== email));
    } catch {
      setError('移除失败');
    } finally {
      setRemoving(null);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-warm-50">
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        {/* 用户信息 */}
        <div className="rounded-2xl border border-warm-200 bg-white p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-11 h-11 rounded-xl bg-amber-100 flex items-center justify-center">
              <ShieldCheck className="w-6 h-6 text-amber-600" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-warm-800">{user?.email || '未登录'}</h1>
              <p className="text-xs text-warm-400">
                角色 {user?.role || 'user'} · 套餐 {user?.plan || 'free'}
              </p>
            </div>
          </div>
        </div>

        {/* 受信邮箱 */}
        <div className="rounded-2xl border border-warm-200 bg-white p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-warm-800">受信邮箱</h2>
              <p className="text-xs text-warm-400 mt-0.5">
                发往受信邮箱的报告无需验证码直达；其他邮箱需验证码验证。
              </p>
            </div>
            <button
              onClick={fetchTrusted}
              disabled={loading}
              className="p-2 rounded-lg border border-warm-200 text-warm-500 hover:bg-warm-50 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {error && (
            <div className="mb-3 p-2.5 text-sm text-terracotta bg-terracotta/10 border border-terracotta/30 rounded-lg">
              {error}
            </div>
          )}
          {notice && (
            <div className="mb-3 p-2.5 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg">
              {notice}
            </div>
          )}

          {/* 添加受信邮箱 */}
          <div className="mb-4 rounded-lg border border-warm-200 bg-warm-50 p-3 space-y-2">
            <div className="flex gap-2">
              <input
                type="email"
                placeholder="新增受信邮箱"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                className="h-10 flex-1 min-w-0 rounded-lg border border-warm-200 bg-white px-3 py-2 text-sm text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
              />
              <button
                type="button"
                onClick={handleSendCode}
                disabled={countdown > 0 || sendingCode || !validEmail}
                className="h-10 shrink-0 rounded-lg border border-warm-200 bg-white px-3 text-xs font-medium text-warm-700 hover:border-amber hover:text-amber disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
              >
                {countdown > 0 ? `${countdown}s 后重发` : sendingCode ? '发送中...' : '发送验证码'}
              </button>
            </div>
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
                onClick={handleVerify}
                disabled={!validEmail || !code.trim()}
                className="flex items-center gap-1 h-10 shrink-0 rounded-lg bg-amber text-white px-3 text-xs font-medium hover:bg-amber-dark disabled:opacity-50 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                添加
              </button>
            </div>
          </div>

          {/* 受信邮箱列表 */}
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-5 h-5 text-warm-400 animate-spin" />
            </div>
          ) : trusted.length === 0 ? (
            <p className="text-sm text-warm-400 text-center py-6">暂无受信邮箱</p>
          ) : (
            <ul className="space-y-2">
              {trusted.map((t) => (
                <li
                  key={t.email}
                  className="flex items-center gap-3 rounded-lg border border-warm-200 px-3 py-2.5"
                >
                  <div className="w-8 h-8 rounded bg-amber-50 flex items-center justify-center flex-shrink-0">
                    <ShieldCheck className="w-4 h-4 text-amber-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-warm-800 truncate">{t.email}</p>
                    <p className="text-[11px] text-warm-400">{sourceLabel(t.source)}</p>
                  </div>
                  <button
                    onClick={() => handleRemove(t.email)}
                    disabled={removing === t.email}
                    className="p-1.5 rounded hover:bg-terracotta/10 text-warm-400 hover:text-terracotta disabled:opacity-50 transition-colors"
                    title="移除"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
