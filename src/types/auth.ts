/** 登录请求 */
export interface LoginRequest {
  email: string;
  password: string;
}

/** 注册请求 */
export interface RegisterRequest {
  email: string;
  password: string;
  /** 邮箱验证码；后端 REQUIRE_EMAIL_VERIFICATION=false 时可省略 */
  code?: string;
}

/** 验证码用途（与后端 VALID_PURPOSES 对齐） */
export type CodePurpose = 'register' | 'login' | 'send_email' | 'bind_email' | 'reset';

/** 发送邮箱验证码请求 */
export interface SendCodeRequest {
  email: string;
  purpose: CodePurpose;
  /** 表单令牌，由 getFormToken() 获取，用于防机器 */
  form_token?: string;
}

/** 验证码登录请求 */
export interface LoginByCodeRequest {
  email: string;
  code: string;
}

/** 受信邮箱验证请求（发送报告到非受信邮箱前，或绑定受信邮箱） */
export interface VerifyCodeRequest {
  email: string;
  purpose: 'send_email' | 'bind_email';
  code: string;
  /** 勾选「记住」→ 登记为受信邮箱 */
  remember?: boolean;
}

/** 受信邮箱验证响应 */
export interface VerifyCodeResponse {
  message: string;
  email: string;
  trusted: boolean;
}

/** 发送邮箱验证码响应 */
export interface SendCodeResponse {
  message: string;
  /** 验证码有效期（秒） */
  expires_in: number;
  /** 可重发的冷却时间（秒） */
  resend_after: number;
}

/** 表单令牌响应（防机器） */
export interface FormTokenResponse {
  token: string;
  /** 需在表单上停留的最少秒数 */
  min_age: number;
  expires_in: number;
}

/** 校验重置验证码请求 */
export interface VerifyResetCodeRequest {
  email: string;
  code: string;
}

/** 校验重置验证码响应（一次性票据） */
export interface VerifyResetCodeResponse {
  reset_token: string;
  expires_in: number;
}

/** 重置密码请求 */
export interface ResetPasswordRequest {
  reset_token: string;
  password: string;
}

/** 登录响应（JWT Token） */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  role?: string;
  plan?: string;
}

/** 注册响应 */
export interface RegisterResponse {
  message: string;
}

/** 当前用户信息 */
export interface UserInfo {
  email: string;
  role: string;
  plan: string;
}
