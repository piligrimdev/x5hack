import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface EconomySummary {
  total_saved: number;
  total_paid: number;
  receipts_count: number;
}

export function useEconomy(token: string | null) {
  const [economy, setEconomy] = useState<EconomySummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    apiFetch<EconomySummary>('/receipts/economy', token)
      .then(setEconomy)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { economy, loading, error, refetch };
}
