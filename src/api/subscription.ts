import client from './client';
import type { AnomalySignal } from '@/types/risk';

export interface SubscriptionItem {
  enterprise_id: string;
  display_label: string;
  industry_l1: string;
  signal_count: number;
  high_count: number;
  material: boolean;
  created_at: string | null;
}

export interface SubscriptionDetectItem {
  enterprise_id: string;
  signals: AnomalySignal[];
  signal_count: number;
  high_count: number;
  material: boolean;
  report_id: string | null;
  pushed: boolean;
  error?: string;
}

export interface SubscriptionDetectResponse {
  user_id: string;
  total: number;
  pushed: number;
  items: SubscriptionDetectItem[];
}

export const subscriptionApi = {
  /** 订阅企业（幂等） */
  subscribe: (enterpriseId: string): Promise<{ subscribed: boolean; enterprise_id: string; already: boolean }> =>
    client.post('/subscriptions', { enterprise_id: enterpriseId }),

  /** 我的订阅列表 */
  list: (): Promise<{ items: SubscriptionItem[]; total: number }> =>
    client.get('/subscriptions'),

  /** 退订 */
  unsubscribe: (enterpriseId: string): Promise<{ unsubscribed: boolean }> =>
    client.delete(`/subscriptions/${enterpriseId}`),

  /** 触发异动检测（实质异动生成报告，可选推送） */
  detect: (sendEmail = false): Promise<SubscriptionDetectResponse> =>
    client.post('/subscriptions/detect', { send_email: sendEmail }),
};
