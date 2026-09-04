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
  items_count: number;
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
