import axios from 'axios';

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 45000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截：注入 JWT Bearer Token
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截
client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 401 时清除 token 并跳转登录
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('isLoggedIn');
      localStorage.removeItem('userEmail');
      // 避免在登录页重复跳转
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    const message = error.response?.data?.detail || error.response?.data?.message || '请求失败，请稍后重试';
    console.error('[API Error]', message);
    return Promise.reject(error);
  }
);

export default client;
