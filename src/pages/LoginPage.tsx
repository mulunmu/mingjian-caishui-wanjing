import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { AnimatedCharacters } from '@/components/ui/AnimatedCharacters';
import { InteractiveHoverButton } from '@/components/ui/InteractiveHoverButton';
import { CuteEyeLogo } from '@/components/ui/CuteEyeLogo';
import useAuthStore from '@/stores/authStore';

type LoginMode = 'password' | 'code';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, loginByCode, demoLogin, sendCode, fetchFormToken, isLoading, error, clearError } =
    useAuthStore();
  const [loginMode, setLoginMode] = useState<LoginMode>('password');
  const [showPassword, setShowPassword] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [isPasswordFieldFocused, setIsPasswordFieldFocused] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [formToken, setFormToken] = useState('');
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    code: '',
  });
  const [formError, setFormError] = useState('');

  useEffect(() => {
    void fetchFormToken().then(setFormToken);
  }, [fetchFormToken]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setFormError('');

    if (loginMode === 'code') {
      if (!formData.email || !formData.code.trim()) {
        setFormError('请输入邮箱和验证码');
        return;
      }
      const success = await loginByCode(formData.email.trim(), formData.code.trim());
      if (success) navigate('/');
      return;
    }

    if (!formData.email || !formData.password) {
      setFormError('请输入邮箱和密码');
      return;
    }

    const success = await login(formData.email, formData.password);
    if (success) {
      navigate('/');
    }
  };

  const handleSendCode = async () => {
    clearError();
    setFormError('');
    const email = formData.email.trim();
    if (!email) {
      setFormError('请先填写邮箱');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setFormError('邮箱格式不正确');
      return;
    }
    setSendingCode(true);
    const res = await sendCode(email, 'login', formToken);
    setSendingCode(false);
    if (!res.ok) {
      setFormError(res.message);
      void fetchFormToken().then(setFormToken);
      return;
    }
    setCountdown(res.resendAfter ?? 60);
  };

  return (
    <div className="min-h-screen max-h-screen overflow-hidden grid lg:grid-cols-2">
      {/* 左侧动画角色区域 - 暖色背景 */}
      <div className="relative hidden lg:flex flex-col justify-between bg-gradient-to-br from-amber-100 via-warm-100 to-orange-50 p-12 text-warm-800">
        {/* Logo 放在右侧上方 */}
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

        {/* 动画角色居中 */}
        <div className="relative z-20 flex items-end justify-center h-[500px]">
          <AnimatedCharacters
            isTyping={isTyping}
            showPassword={showPassword}
            passwordLength={formData.password.length}
            isPasswordFieldFocused={isPasswordFieldFocused}
          />
        </div>

        {/* 装饰元素 - 暖色系 */}
        <div className="absolute inset-0 bg-grid-warm/[0.05] bg-[size:20px_20px]" />
        <div className="absolute top-1/4 right-1/4 size-64 bg-amber/10 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 left-1/4 size-96 bg-orange-200/20 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/3 size-48 bg-warm-200/30 rounded-full blur-2xl" />
      </div>

      {/* 右侧登录表单 */}
      <div className="flex items-center justify-center p-8 bg-warm-50">
        <div className="w-full max-w-[420px]">
          {/* 移动端Logo */}
          <div className="lg:hidden flex items-center justify-center gap-4 mb-12">
            <div className="w-20 h-20 rounded-2xl bg-amber/10 shadow-warm-sm flex items-center justify-center">
              <CuteEyeLogo size={64} />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-warm-800">明鉴・财税票・万景</h2>
              <p className="text-sm text-warm-500">财税票智能风控报告产品</p>
            </div>
          </div>

          {/* 标题 */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold tracking-tight mb-2 text-warm-800">
              欢迎回来！
            </h1>
            <p className="text-warm-500 text-sm">请输入您的账号信息</p>
          </div>

          {/* 登录方式切换 */}
          <div className="flex rounded-lg bg-warm-100 p-1 mb-6">
            <button
              type="button"
              onClick={() => {
                setLoginMode('password');
                setFormError('');
              }}
              className={`flex-1 h-9 rounded-md text-sm font-medium transition-colors ${
                loginMode === 'password'
                  ? 'bg-white text-warm-800 shadow-sm'
                  : 'text-warm-500 hover:text-warm-700'
              }`}
            >
              密码登录
            </button>
            <button
              type="button"
              onClick={() => {
                setLoginMode('code');
                setFormError('');
              }}
              className={`flex-1 h-9 rounded-md text-sm font-medium transition-colors ${
                loginMode === 'code'
                  ? 'bg-white text-warm-800 shadow-sm'
                  : 'text-warm-500 hover:text-warm-700'
              }`}
            >
              验证码登录
            </button>
          </div>

          {/* 登录表单 */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-warm-700">
                邮箱
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

            {loginMode === 'password' && (
              <div className="space-y-2">
                <label htmlFor="password" className="text-sm font-medium text-warm-700">
                  密码
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="••••••••"
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
            )}

            {loginMode === 'code' && (
              <div className="space-y-2">
                <label htmlFor="code" className="text-sm font-medium text-warm-700">
                  邮箱验证码
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
            )}

            {(error || formError) && (
              <div className="p-3 text-sm text-terracotta bg-terracotta/10 border border-terracotta/30 rounded-lg">
                {error || formError}
              </div>
            )}

            <InteractiveHoverButton
              type="submit"
              text={isLoading ? '登录中...' : loginMode === 'code' ? '验证码登录' : '登录'}
              className="w-full h-12 text-base font-medium"
              disabled={isLoading}
            />
          </form>

          {/* 测试账号登录 */}
          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-warm-200" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="px-2 bg-warm-50 text-warm-400">或</span>
              </div>
            </div>

            <InteractiveHoverButton
              type="button"
              text={isLoading ? '登录中...' : '使用演示账号登录'}
              className="w-full h-12 mt-4 border-warm-300"
              disabled={isLoading}
              onClick={async () => {
                clearError();
                setFormError('');
                const success = await demoLogin();
                if (success) navigate('/');
              }}
              icon={
                <svg
                  className="h-5 w-5"
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
                  <polyline points="10 17 15 12 10 7" />
                  <line x1="15" y1="12" x2="3" y2="12" />
                </svg>
              }
            />
            <p className="mt-2 text-center text-[11px] text-warm-400">
              演示登录由服务端签发（DEMO_LOGIN_ENABLED），前端不携带口令
            </p>
          </div>

          {/* 注册链接 */}
          <div className="text-center text-sm text-warm-500 mt-8">
            还没有账号？{' '}
            <Link
              to="/register"
              className="text-warm-800 font-medium hover:text-amber transition-colors"
            >
              立即注册
            </Link>
          </div>

          {/* 忘记密码 */}
          <div className="text-center text-sm text-warm-500 mt-3">
            忘记了密码？{' '}
            <Link
              to="/forgot-password"
              className="text-warm-800 font-medium hover:text-amber transition-colors"
            >
              重置密码
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
