import client from './client';
import type { LoginRequest, TokenResponse, RegisterRequest, RegisterResponse } from '@/types/auth';

export const authApi = {
  /** 登录：获取 JWT Token */
  login: (params: LoginRequest): Promise<TokenResponse> =>
    client.post('/auth/login', params),

  /** 演示一键登录（服务端签发，前端不携带口令） */
  demoLogin: (): Promise<TokenResponse & { email?: string }> =>
    client.post('/auth/demo-login', {}),

  /** 注册 */
  register: (params: RegisterRequest): Promise<RegisterResponse> =>
    client.post('/auth/register', params),
};
