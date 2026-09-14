import { create } from 'zustand';
import { authApi } from '@/api/auth';
import type { CodePurpose, UserInfo } from '@/types/auth';
import useChatStore, { clearChatLocalCache } from '@/stores/chatStore';

interface AuthStore {
  isLoggedIn: boolean;
  user: UserInfo | null;
  isLoading: boolean;
  error: string;

  login: (email: string, password: string) => Promise<boolean>;
  loginByCode: (email: string, code: string) => Promise<boolean>;
  demoLogin: () => Promise<boolean>;
  register: (email: string, password: string, code?: string) => Promise<boolean>;
  fetchFormToken: () => Promise<string>;
  sendCode: (
    email: string,
    purpose?: CodePurpose,
    formToken?: string,
  ) => Promise<{ ok: boolean; message: string; resendAfter?: number }>;
  /** 受信邮箱验证：校验验证码；成功可登记受信邮箱 */
  verifyCode: (
    email: string,
    purpose: 'send_email' | 'bind_email',
    code: string,
    remember?: boolean,
  ) => Promise<{ ok: boolean; message: string; trusted?: boolean }>;
  /** 校验重置验证码 → 换取一次性 reset_token；失败返回 ok:false */
  verifyResetCode: (
    email: string,
    code: string,
  ) => Promise<{ ok: boolean; message: string; resetToken?: string }>;
  /** 凭 reset_token 重置密码 */
  resetPassword: (resetToken: string, password: string) => Promise<{ ok: boolean; message: string }>;
  logout: () => void;
  clearError: () => void;
  checkAuth: () => void;
}

/**
 * 提取后端错误文案。
 * FastAPI 的 detail 有两种形状：业务错误是 string，请求校验失败（422）是数组。
 * 既有代码只按 string 取，遇到 422 会得到 [object Object]，这里做统一收敛。
 */
function extractDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  return fallback;
}

/** 从 JWT payload 读取 role/plan（UI 展示）；真正授权仍以服务端 require_plan 为准。 */
function userFromToken(token: string, fallbackEmail?: string): UserInfo | null {
  try {
    const part = token.split('.')[1];
    if (!part) return null;
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'));
    const payload = JSON.parse(json) as { sub?: string; role?: string; plan?: string };
    const email = (payload.sub || fallbackEmail || '').trim();
    if (!email) return null;
    return {
      email,
      role: payload.role || 'user',
      plan: payload.plan || 'free',
    };
  } catch {
    return null;
  }
}

const useAuthStore = create<AuthStore>((set) => ({
  isLoggedIn: localStorage.getItem('isLoggedIn') === 'true',
  user: null,
  isLoading: false,
  error: '',

  checkAuth: () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      set({ isLoggedIn: false, user: null });
      return;
    }
    const fromJwt = userFromToken(token, localStorage.getItem('userEmail') || undefined);
    if (!fromJwt) {
      set({ isLoggedIn: false, user: null });
      return;
    }
    // 同步缓存仅作展示；门槛以 JWT 内 plan/role 为准，防 localStorage.userPlan 篡改
    localStorage.setItem('userEmail', fromJwt.email);
    localStorage.setItem('userRole', fromJwt.role);
    localStorage.setItem('userPlan', fromJwt.plan);
    set({ isLoggedIn: true, user: fromJwt });
  },

  login: async (email, password) => {
    set({ isLoading: true, error: '' });
    try {
      const res = await authApi.login({ email, password });
      localStorage.setItem('access_token', res.access_token);
      localStorage.setItem('isLoggedIn', 'true');
      const user =
        userFromToken(res.access_token, email) || {
          email,
          role: res.role || 'user',
          plan: res.plan || 'free',
        };
      localStorage.setItem('userEmail', user.email);
      localStorage.setItem('userRole', user.role);
      localStorage.setItem('userPlan', user.plan);
      set({
        isLoggedIn: true,
        user,
        isLoading: false,
      });
      return true;
    } catch (err: unknown) {
      set({ error: extractDetail(err, '登录失败，请重试'), isLoading: false });
      return false;
    }
  },

  loginByCode: async (email, code) => {
    set({ isLoading: true, error: '' });
    try {
      const res = await authApi.loginByCode({ email, code });
      localStorage.setItem('access_token', res.access_token);
      localStorage.setItem('isLoggedIn', 'true');
      const user =
        userFromToken(res.access_token, email) || {
          email,
          role: res.role || 'user',
          plan: res.plan || 'free',
        };
      localStorage.setItem('userEmail', user.email);
      localStorage.setItem('userRole', user.role);
      localStorage.setItem('userPlan', user.plan);
      set({ isLoggedIn: true, user, isLoading: false });
      return true;
    } catch (err: unknown) {
      set({ error: extractDetail(err, '验证码登录失败，请重试'), isLoading: false });
      return false;
    }
  },

  demoLogin: async () => {
    set({ isLoading: true, error: '' });
    try {
      const res = await authApi.demoLogin();
      const email = res.email || 'demo';
      localStorage.setItem('access_token', res.access_token);
      localStorage.setItem('isLoggedIn', 'true');
      const user =
        userFromToken(res.access_token, email) || {
          email,
          role: res.role || 'user',
          plan: res.plan || 'free',
        };
      localStorage.setItem('userEmail', user.email);
      localStorage.setItem('userRole', user.role);
      localStorage.setItem('userPlan', user.plan);
      set({
        isLoggedIn: true,
        user,
        isLoading: false,
      });
      return true;
    } catch (err: unknown) {
      set({
        error: extractDetail(err, '演示登录失败，请确认 DEMO_LOGIN_ENABLED=true'),
        isLoading: false,
      });
      return false;
    }
  },

  register: async (email, password, code) => {
    set({ isLoading: true, error: '' });
    try {
      await authApi.register(code ? { email, password, code } : { email, password });
      set({ isLoading: false });
      return true;
    } catch (err: unknown) {
      set({ error: extractDetail(err, '注册失败，请重试'), isLoading: false });
      return false;
    }
  },

  /** 获取防机器表单令牌；失败返回空串（调用方按「令牌缺失」处理，后端会拒绝） */
  fetchFormToken: async () => {
    try {
      const res = await authApi.formToken();
      return res.token || '';
    } catch {
      return '';
    }
  },

  sendCode: async (email, purpose = 'register', formToken) => {
    try {
      const res = await authApi.sendCode({ email, purpose, form_token: formToken });
      return { ok: true, message: res.message, resendAfter: res.resend_after };
    } catch (err: unknown) {
      return { ok: false, message: extractDetail(err, '验证码发送失败，请重试') };
    }
  },

  verifyCode: async (email, purpose, code, remember) => {
    try {
      const res = await authApi.verifyCode({ email, purpose, code, remember });
      return { ok: true, message: res.message, trusted: res.trusted };
    } catch (err: unknown) {
      return { ok: false, message: extractDetail(err, '验证码校验失败，请重试') };
    }
  },

  verifyResetCode: async (email, code) => {
    try {
      const res = await authApi.verifyResetCode({ email, code });
      return { ok: true, message: '验证通过', resetToken: res.reset_token };
    } catch (err: unknown) {
      return { ok: false, message: extractDetail(err, '验证码校验失败，请重试') };
    }
  },

  resetPassword: async (resetToken, password) => {
    try {
      const res = await authApi.resetPassword({ reset_token: resetToken, password });
      return { ok: true, message: res.message };
    } catch (err: unknown) {
      return { ok: false, message: extractDetail(err, '密码重置失败，请重试') };
    }
  },

  logout: () => {
    const email = localStorage.getItem('userEmail');
    localStorage.removeItem('access_token');
    localStorage.removeItem('isLoggedIn');
    localStorage.removeItem('userEmail');
    localStorage.removeItem('userName');
    localStorage.removeItem('userRole');
    localStorage.removeItem('userPlan');
    // M0：登出清聊天 localStorage，并重置内存会话（不删服务端历史）
    clearChatLocalCache(email);
    useChatStore.getState().resetLocalChat();
    set({ isLoggedIn: false, user: null });
  },

  clearError: () => set({ error: '' }),
}));

export default useAuthStore;
