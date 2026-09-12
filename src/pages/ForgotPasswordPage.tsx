import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { AnimatedCharacters } from '@/components/ui/AnimatedCharacters';
import { InteractiveHoverButton } from '@/components/ui/InteractiveHoverButton';
import { CuteEyeLogo } from '@/components/ui/CuteEyeLogo';
import useAuthStore from '@/stores/authStore';

/**
 * 重置密码页。
 *
 * 流程：填邮箱 → 获取验证码 → 回填验证码 → 设新密码。
 * 提交时先 POST /auth/verify-reset-code 换取一次性 reset_token，
 * 再 POST /auth/reset-password —— 服务端只认 reset_token，不认验证码本身，
 * 避免「知道邮箱即可改他人密码」。
 */
export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const { sendCode, fetchFormToken, verifyResetCode, resetPassword, clearError } =
    useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [isPasswordFieldFocused, setIsPasswordFieldFocused] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [formToken, setFormToken] = useState('');
  const [formData, setFormData] = useState({
    email: '',
    code: '',
    password: '',
    confirmPassword: '',
  });
  const [localError, setLocalError] = useState('');

  useEffect(() => {
    void fetchFormToken().then(setFormToken);
  }, [fetchFormToken]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const handleSendCode = async () => {
    clearError();
    setLocalError('');
    const email = formData.email.trim();
    if (!email) {
      setLocalError('请先填写邮箱');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setLocalError('邮箱格式不正确');
      return;
    }
    setSendingCode(true);
    const res = await sendCode(email, 'reset', formToken);
    setSendingCode(false);
    if (!res.ok) {
      setLocalError(res.message);
      void fetchFormToken().then(setFormToken);
      return;
    }
    setCountdown(res.resendAfter ?? 60);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setLocalError('');

    if (!formData.email || !formData.code.trim()) {
      setLocalError('请填写邮箱和验证码');
      return;
    }
    if (!formData.password) {
      setLocalError('请填写新密码');
      return;
    }
    if (formData.password !== formData.confirmPassword) {
      setLocalError('两次输入的密码不一致');
      return;
    }
    if (formData.password.length < 6) {
      setLocalError('密码长度至少为6位');
      return;
    }

    setSubmitting(true);
    const verified = await verifyResetCode(formData.email.trim(), formData.code.trim());
    if (!verified.ok || !verified.resetToken) {
      setSubmitting(false);
      setLocalError(verified.message);
      return;
    }
    const done = await resetPassword(verified.resetToken, formData.password);
    setSubmitting(false);
    if (!done.ok) {
      setLocalError(done.message);
      return;
    }
    navigate('/login');
  };

  const displayError = localError;

  return (
    <div className="min-h-screen max-h-screen overflow-hidden grid lg:grid-cols-2">
      <div className="relative hidden lg:flex flex-col justify-between bg-gradient-to-br from-amber-100 via-warm-100 to-orange-50 p-12 text-warm-800">
        <div className="relative z-20 flex justify-end">
          <div className="flex items-center gap-4">
            <div className="text-right">
              <h2 className="text-2xl font-bold text-warm-800">明鉴・财税票・万景</h2>
              <p className="text-sm text-warm-500">财税票智能风控报告产品</p>
            </div>
            <div className="w-20 h-20 rounded-2xl bg-white/80 backdrop-blur-sm shadow-warm-md flex items-center justify-center p-2">
              <CuteEyeLogo size={64} />
            </div>
          </div>
        </div>

        <div className="relative z-20 flex items-end justify-center h-[500px]">
          <AnimatedCharacters
            isTyping={isTyping}
            showPassword={showPassword || showConfirmPassword}
            passwordLength={formData.password.length + formData.confirmPassword.length}
            isPasswordFieldFocused={isPasswordFieldFocused}
          />
        </div>

        <div className="absolute inset-0 bg-grid-warm/[0.05] bg-[size:20px_20px]" />
        <div className="absolute top-1/4 right-1/4 size-64 bg-amber/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 size-96 bg-orange-200/20 rounded-full blur-3xl" />
      </div>

      <div className="flex items-center justify-center p-8 bg-warm-50 overflow-y-auto">
        <div className="w-full max-w-[420px]">
          <div className="lg:hidden flex items-center justify-center gap-4 mb-8">
            <div className="w-20 h-20 rounded-2xl bg-amber/10 shadow-warm-sm flex items-center justify-center">
              <CuteEyeLogo size={64} />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-warm-800">明鉴・财税票・万景</h2>
              <p className="text-sm text-warm-500">财税票智能风控报告产品</p>
            </div>
          </div>

          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold tracking-tight mb-2 text-warm-800">
              重置密码
            </h1>
            <p className="text-warm-500 text-sm">验证邮箱后设置新密码</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-warm-700">
                邮箱 <span className="text-terracotta">*</span>
              </label>
              <input
                id="email"
                type="email"
                placeholder="you@example.com"
                autoComplete="off"
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
                onFocus={() => setIsTyping(true)}
                onBlur={() => setIsTyping(false)}
                className="h-12 w-full rounded-lg border border-warm-200 bg-white px-4 py-2 text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="code" className="text-sm font-medium text-warm-700">
                邮箱验证码 <span className="text-terracotta">*</span>
              </label>
              <div className="flex gap-2">
                <input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="6 位数字"
                  autoComplete="off"
                  value={formData.code}
                  onChange={(e) =>
                    setFormData({ ...formData, code: e.target.value.replace(/\D/g, '') })
                  }
                  onFocus={() => setIsTyping(true)}
                  onBlur={() => setIsTyping(false)}
                  className="h-12 flex-1 min-w-0 rounded-lg border border-warm-200 bg-white px-4 py-2 text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
                />
                <button
                  type="button"
                  onClick={handleSendCode}
                  disabled={countdown > 0 || sendingCode || !formData.email}
                  className="h-12 shrink-0 rounded-lg border border-warm-200 bg-white px-4 text-sm font-medium text-warm-700 transition-colors hover:border-amber hover:text-amber disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {countdown > 0 ? `${countdown}s 后重发` : sendingCode ? '发送中...' : '获取验证码'}
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium text-warm-700">
                新密码 <span className="text-terracotta">*</span>
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="至少6位密码"
                  value={formData.password}
                  onChange={(e) =>
                    setFormData({ ...formData, password: e.target.value })
                  }
                  onFocus={() => {
                    setIsTyping(true);
                    setIsPasswordFieldFocused(true);
                  }}
                  onBlur={() => {
                    setIsTyping(false);
                    setIsPasswordFieldFocused(false);
                  }}
                  className="h-12 w-full rounded-lg border border-warm-200 bg-white px-4 py-2 pr-12 text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-warm-400 hover:text-warm-600 transition-colors"
                >
                  {showPassword ? (
                    <EyeOff className="size-5" />
                  ) : (
                    <Eye className="size-5" />
                  )}
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="confirmPassword" className="text-sm font-medium text-warm-700">
                确认密码 <span className="text-terracotta">*</span>
              </label>
              <div className="relative">
                <input
                  id="confirmPassword"
                  type={showConfirmPassword ? 'text' : 'password'}
                  placeholder="再次输入新密码"
                  value={formData.confirmPassword}
                  onChange={(e) =>
                    setFormData({ ...formData, confirmPassword: e.target.value })
                  }
                  onFocus={() => {
                    setIsTyping(true);
                    setIsPasswordFieldFocused(true);
                  }}
                  onBlur={() => {
                    setIsTyping(false);
                    setIsPasswordFieldFocused(false);
                  }}
                  className="h-12 w-full rounded-lg border border-warm-200 bg-white px-4 py-2 pr-12 text-warm-800 placeholder:text-warm-400 focus:outline-none focus:border-amber focus:ring-1 focus:ring-amber transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-warm-400 hover:text-warm-600 transition-colors"
                >
                  {showConfirmPassword ? (
                    <EyeOff className="size-5" />
                  ) : (
                    <Eye className="size-5" />
                  )}
                </button>
              </div>
            </div>

            {displayError && (
              <div className="p-3 text-sm text-terracotta bg-terracotta/10 border border-terracotta/30 rounded-lg">
                {displayError}
              </div>
            )}

            <div className="pt-2">
              <InteractiveHoverButton
                type="submit"
                text={submitting ? '提交中...' : '重置密码'}
                className="w-full h-12 text-base font-medium"
                disabled={submitting}
              />
            </div>
          </form>

          <div className="text-center text-sm text-warm-500 mt-8">
            <Link
              to="/login"
              className="text-warm-800 font-medium hover:text-amber transition-colors"
            >
              返回登录
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
