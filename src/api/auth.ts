import client from './client';
import type {
  LoginRequest,
  TokenResponse,
  RegisterRequest,
  RegisterResponse,
  SendCodeRequest,
  SendCodeResponse,
  FormTokenResponse,
  VerifyResetCodeRequest,
  VerifyResetCodeResponse,
  ResetPasswordRequest,
} from '@/types/auth';

export const authApi = {
  /** 登录：获取 JWT Token */
  login: (params: LoginRequest): Promise<TokenResponse> =>
    client.post('/auth/login', params),

  /** 演示一键登录（服务端签发，前端不携带口令） */
  demoLogin: (): Promise<TokenResponse & { email?: string }> =>
    client.post('/auth/demo-login', {}),

  /** 获取防机器用的表单令牌（打开表单时取一次） */
  formToken: (): Promise<FormTokenResponse> => client.get('/auth/form-token'),

  /** 发送邮箱验证码 */
  sendCode: (params: SendCodeRequest): Promise<SendCodeResponse> =>
    client.post('/auth/send-code', params),

  /** 校验重置验证码，换取一次性 reset_token */
  verifyResetCode: (params: VerifyResetCodeRequest): Promise<VerifyResetCodeResponse> =>
    client.post('/auth/verify-reset-code', params),

  /** 凭 reset_token 重置密码 */
  resetPassword: (params: ResetPasswordRequest): Promise<RegisterResponse> =>
    client.post('/auth/reset-password', params),

  /** 注册 */
  register: (params: RegisterRequest): Promise<RegisterResponse> =>
    client.post('/auth/register', params),
};
