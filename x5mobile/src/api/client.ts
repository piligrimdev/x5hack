export const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function readDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
}

function authPayload(phone: string, referralCode?: string): Record<string, string> {
  const payload: Record<string, string> = { phone };
  if (referralCode) payload.referral_code = referralCode;
  return payload;
}

export async function apiFetch<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${body}`);
  }
  return res.json() as Promise<T>;
}

export async function apiLogin(phone: string, referralCode?: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(authPayload(phone, referralCode)),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, readDetail(body, 'Номер не найден'));
  }
  const data = await res.json();
  return data.access_token as string;
}

export async function apiRegister(phone: string, referralCode?: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(authPayload(phone, referralCode)),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, readDetail(body, 'Ошибка регистрации'));
  }
  const data = await res.json();
  return data.access_token as string;
}

export type ReferralStatus = 'issued' | 'awaiting_purchase' | 'rewarded' | 'expired';

export interface ReferralOut {
  id: string;
  code: string;
  status: ReferralStatus;
  created_at: string;
  activated_at: string | null;
  discount_valid_to: string | null;
  purchase_window_until: string | null;
  reward_status: 'awaiting_purchase' | 'rewarded' | null;
}

export interface ReferralListOut {
  items: ReferralOut[];
}

export async function apiIssueReferral(token: string): Promise<ReferralOut> {
  return apiFetch<ReferralOut>('/referrals', token, { method: 'POST', body: '{}' });
}

export async function apiListReferrals(token: string): Promise<ReferralListOut> {
  return apiFetch<ReferralListOut>('/referrals', token);
}

export interface UserDiscountOut {
  id: string;
  title: string;
  description: string;
  value: number;
  discount_type: string;
  link_type: string;
  is_personal: boolean;
  valid_from: string | null;
  valid_to: string | null;
}

export interface UserDiscountListOut {
  items: UserDiscountOut[];
}

export async function apiListAvailableDiscounts(token: string): Promise<UserDiscountListOut> {
  return apiFetch<UserDiscountListOut>('/discounts/available', token);
}

export type CouponTxType =
  | 'weekly_grant'
  | 'task_complete'
  | 'spin'
  | 'referral'
  | 'purchase';

export interface CouponTxOut {
  id: string;
  type: CouponTxType;
  amount: number;
  related_task_id: string | null;
  related_spin_id: string | null;
  related_referral_link_id: string | null;
  related_receipt_id: string | null;
  week_start: string | null;
  created_at: string;
}

export interface CouponTxPage {
  items: CouponTxOut[];
  limit: number;
  offset: number;
  total: number;
}

export async function apiListCouponTransactions(
  token: string,
  limit = 20,
  offset = 0,
): Promise<CouponTxPage> {
  return apiFetch<CouponTxPage>(`/coupons/transactions?limit=${limit}&offset=${offset}`, token);
}
