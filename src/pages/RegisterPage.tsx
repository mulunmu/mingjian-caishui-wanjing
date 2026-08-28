import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { AnimatedCharacters } from '@/components/ui/AnimatedCharacters';
import { InteractiveHoverButton } from '@/components/ui/InteractiveHoverButton';
import { CuteEyeLogo } from '@/components/ui/CuteEyeLogo';
import useAuthStore from '@/stores/authStore';

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register, isLoading, error, clearError } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [isPasswordFieldFocused, setIsPasswordFieldFocused] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [localError, setLocalError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setLocalError('');

    if (!formData.email || !formData.password) {
      setLocalError('请填写邮箱和密码');
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

    const success = await register(formData.email, formData.password);
    if (success) {
      navigate('/login');
    }
  };

  const displayError = localError || error;

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
              创建账号
            </h1>
            <p className="text-warm-500 text-sm">开始使用财税票智能风控报告产品</p>
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
              <label htmlFor="password" className="text-sm font-medium text-warm-700">
                密码 <span className="text-terracotta">*</span>
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
                  placeholder="再次输入密码"
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
                text={isLoading ? '注册中...' : '注册'}
                className="w-full h-12 text-base font-medium"
                disabled={isLoading}
              />
            </div>
          </form>

          <p className="text-xs text-warm-400 text-center mt-4">
            注册即表示您同意我们的{' '}
            <a href="#" className="text-amber hover:underline">服务条款</a>
            {' '}和{' '}
            <a href="#" className="text-amber hover:underline">隐私政策</a>
          </p>

          <div className="text-center text-sm text-warm-500 mt-6">
            已有账号？{' '}
            <Link
              to="/login"
              className="text-warm-800 font-medium hover:text-amber transition-colors"
            >
              立即登录
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
