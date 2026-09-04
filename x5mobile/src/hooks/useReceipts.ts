import { useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface ReceiptListItem {
  id: string;
  purchase_date: string;
  store_id: string;
  store_geo_cluster: string;
  store_format_name: string;
  total_base: number;
  total_paid: number;
  total_saved: number;
  discount_saved_rub: number;
  cashback_applied_points: number;
  cashback_applied_rub: number;
  items_count: number;
}

/** Экономия по чеку: скидки + списанные бонусы. */
export function receiptSavedRub(r: {
  discount_saved_rub?: number;
  cashback_applied_rub?: number;
  total_saved?: number;
}): number {
  const discount = r.discount_saved_rub ?? 0;
  const cashback = r.cashback_applied_rub ?? 0;
  if (r.discount_saved_rub != null || r.cashback_applied_rub != null) {
    return discount + cashback;
  }
  return r.total_saved ?? 0;
}

export function useReceipts(token: string | null) {
  const [receipts, setReceipts] = useState<ReceiptListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    apiFetch<{ items: ReceiptListItem[]; total: number; page: number; size: number }>(
      '/receipts?size=50',
      token,
    )
      .then((data) => setReceipts(data.items))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  return { receipts, loading, error };
}
