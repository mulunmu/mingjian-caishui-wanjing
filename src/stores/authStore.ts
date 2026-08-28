import { create } from 'zustand';
import { authApi } from '@/api/auth';
import type { UserInfo } from '@/types/auth';

interface AuthStore {
  isLoggedIn: boolean;
  user: UserInfo | null;
  isLoading: boolean;
  error: string;

  login: (email: string, password: string) => Promise<boolean>;
  register: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
  checkAuth: () => void;
}

const useAuthStore = create<AuthStore>((set) => ({
  isLoggedIn: localStorage.getItem('isLoggedIn') === 'true',
  user: null,
  isLoading: false,
  error: '',

  checkAuth: () => {
    const token = localStorage.getItem('access_token');
    const email = localStorage.getItem('userEmail');
    if (token && email) {
      set({ isLoggedIn: true, user: { email } });
    } else {
      set({ isLoggedIn: false, user: null });
    }
  },

  login: async (email, password) => {
    set({ isLoading: true, error: '' });
    try {
      const res = await authApi.login({ email, password });
      localStorage.setItem('access_token', res.access_token);
      localStorage.setItem('isLoggedIn', 'true');
      localStorage.setItem('userEmail', email);
      set({ isLoggedIn: true, user: { email }, isLoading: false });
      return true;
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '登录失败，请重试';
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
    set({ isLoggedIn: false, user: null });
  },

  clearError: () => set({ error: '' }),
}));

export default useAuthStore;
