/** 发送记录（EmailLog，全程审计） */
export interface EmailLogItem {
  id: number;
  owner: string | null;
  sender: string;
  recipient: string;
  subject: string;
  report_id: string | null;
  kind: 'report' | 'verify_code';
  provider: string;
  status: 'pending' | 'sent' | 'failed';
  message_id: string | null;
  error: string | null;
  retry_count: number;
  created_at: string;
  sent_at: string | null;
}

/** 发送记录列表响应 */
export interface EmailLogListResponse {
  items: EmailLogItem[];
  total: number;
}

/** 发送单份报告请求（/emails/send） */
export interface SendEmailRequest {
  report_id: string;
  recipient: string;
  /** 非受信邮箱需验证码 */
  code?: string;
  /** 勾选「记住」→ 登记为受信邮箱 */
  remember?: boolean;
}

/** 批量发送请求（/emails/batch） */
export interface BatchEmailRequest {
  report_ids: string[];
  recipient: string;
  code?: string;
  remember?: boolean;
}

/** 发送响应 */
export interface SendEmailResponse {
  success: boolean;
  message: string;
  log_id?: number;
}

/** 批量发送响应 */
export interface BatchEmailResponse {
  success: boolean;
  sent: number;
  failed: number;
  results: Array<{ report_id: string; ok: boolean; message: string }>;
}

/** 受信邮箱项 */
export interface TrustedEmailItem {
  email: string;
  source: 'register' | 'verified';
  verified_at: string | null;
}

/** 受信邮箱列表响应 */
export interface TrustedEmailListResponse {
  items: TrustedEmailItem[];
  total: number;
}
