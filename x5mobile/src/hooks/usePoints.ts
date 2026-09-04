import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface PointsBalance {
  balance: number;
  rate_points_per_rub: number;
  balance_rub_equivalent: number;
}

export interface PointsTransaction {
  id: string;
  type: 'earn' | 'spend';
  amount: number;
  related_task_id: string | null;
  related_receipt_id: string | null;
  rate_at_time: number | null;
  created_at: string;
}

export interface PointsTransactionsPage {
  items: PointsTransaction[];
  limit: number;
  offset: number;
  total: number;
}

export function usePointsBalance(token: string | null) {
  const [balance, setBalance] = useState<PointsBalance | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBalance = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<PointsBalance>('/points/balance', token);
      setBalance(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки баланса');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchBalance();
  }, [fetchBalance]);

  return { balance, loading, error, refresh: fetchBalance };
}

export function usePointsTransactions(token: string | null, limit = 20) {
  const [page, setPage] = useState<PointsTransactionsPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTx = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<PointsTransactionsPage>(
        `/points/transactions?limit=${limit}&offset=0`,
        token,
      );
      setPage(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки истории');
    } finally {
      setLoading(false);
    }
  }, [token, limit]);

  useEffect(() => {
    fetchTx();
  }, [fetchTx]);

  return { page, loading, error, refresh: fetchTx };
}
