import client from './client';
import type { LoginRequest, TokenResponse, RegisterRequest, RegisterResponse } from '@/types/auth';

export const authApi = {
  /** 登录：获取 JWT Token */
  login: (params: LoginRequest): Promise<TokenResponse> =>
    client.post('/auth/login', params),

  /** 注册 */
  register: (params: RegisterRequest): Promise<RegisterResponse> =>
    client.post('/auth/register', params),
};
