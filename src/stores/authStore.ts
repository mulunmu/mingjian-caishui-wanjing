import { create } from 'zustand';
import { authApi } from '@/api/auth';
import type { UserInfo } from '@/types/auth';

interface AuthStore {
  isLoggedIn: boolean;
  user: UserInfo | null;
  isLoading: boolean;
  error: string;

  login: (email: string, password: string) => Promise<boolean>;
  demoLogin: () => Promise<boolean>;
  register: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
  checkAuth: () => void;
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
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '登录失败，请重试';
      set({ error: message, isLoading: false });
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
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        '演示登录失败，请确认 DEMO_LOGIN_ENABLED=true';
      set({ error: message, isLoading: false });
      return false;
    }
  },

  register: async (email, password) => {
    set({ isLoading: true, error: '' });
    try {
      await authApi.register({ email, password });
      set({ isLoading: false });
      return true;
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '注册失败，请重试';
      set({ error: message, isLoading: false });
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('isLoggedIn');
    localStorage.removeItem('userEmail');
    localStorage.removeItem('userName');
    localStorage.removeItem('userRole');
    localStorage.removeItem('userPlan');
    set({ isLoggedIn: false, user: null });
  },

  clearError: () => set({ error: '' }),
}));

export default useAuthStore;
