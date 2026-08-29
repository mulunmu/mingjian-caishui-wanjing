/** 登录请求 */
export interface LoginRequest {
  email: string;
  password: string;
}

/** 注册请求 */
export interface RegisterRequest {
  email: string;
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
