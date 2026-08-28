import type { UserInfo } from '@/types/auth';

/**
 * 是否需要升级（定制功能门槛）。
 * - 未登录（演示态 AUTH_REQUIRED=false）：不拦截，交给后端判定
 * - 已登录：admin 或 plan=subscriber 放行，其余触发升级弹窗
 */
export function needsUpgrade(user: UserInfo | null | undefined): boolean {
  if (!user) return false;
  return user.role !== 'admin' && user.plan !== 'subscriber';
}

/** 是否定制用户（admin 或 subscriber） */
export function isSubscriber(user: UserInfo | null | undefined): boolean {
  if (!user) return false;
  return user.role === 'admin' || user.plan === 'subscriber';
}
