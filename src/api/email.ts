import client from './client';
import type {
  SendEmailRequest,
  SendEmailResponse,
  BatchEmailRequest,
  BatchEmailResponse,
  EmailLogListResponse,
  TrustedEmailListResponse,
} from '@/types/email';

export const emailApi = {
  /** 发送单份报告到指定收件人（受信直达 / 未受信需验证码） */
  send: (params: SendEmailRequest): Promise<SendEmailResponse> =>
    client.post('/emails/send', params),

  /** 批量发送多份报告到同一收件人 */
  batch: (params: BatchEmailRequest): Promise<BatchEmailResponse> =>
    client.post('/emails/batch', params),

  /** 我的发送记录（分页） */
  logs: (params?: {
    recipient?: string;
    kind?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<EmailLogListResponse> => client.get('/emails/logs', { params }),

  /** 重发一封报告邮件 */
  resend: (logId: number): Promise<SendEmailResponse> =>
    client.post(`/emails/${logId}/resend`),

  /** 受信邮箱列表 */
  listTrusted: (): Promise<TrustedEmailListResponse> =>
    client.get('/emails/trusted'),

  /** 移除受信邮箱 */
  removeTrusted: (email: string): Promise<{ success: boolean; message: string }> =>
    client.delete(`/emails/trusted/${encodeURIComponent(email)}`),
};
