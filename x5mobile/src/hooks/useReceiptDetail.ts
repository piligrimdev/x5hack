import { useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface ReceiptDetailItem {
  product_id: string;
  product_name: string;
  quantity: number;
  base_price_at_purchase: number;
  paid_price: number;
  discounted_amount: number;
  discount_id: string | null;
}

export interface ReceiptDetail {
  id: string;
  purchase_date: string;
  store: { id: string; format_name: string; geo_cluster: string };
  channel: string;
  items: ReceiptDetailItem[];
  total_base: number;
  total_paid: number;
  total_saved: number;
}

export function useReceiptDetail(token: string | null, receiptId: string | null) {
  const [detail, setDetail] = useState<ReceiptDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !receiptId) return;
    setLoading(true);
    setError(null);
    apiFetch<ReceiptDetail>(`/receipts/${receiptId}`, token)
      .then(setDetail)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, receiptId]);

  return { detail, loading, error };
}
