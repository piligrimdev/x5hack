import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface ChallengeItem {
  id: string;
  title: string;
  description: string;
  mechanic: string;
  reward_rub: number;
  criterion_type: string;
  criterion_entity_id: string;
  quantity_target: number;
  quantity_current: number;
  deadline: string;
  status: string;
}

export interface PastChallengeItem {
  id: string;
  title: string;
  description: string;
  mechanic: string;
  reward_rub: number;
  criterion_type: string;
  criterion_entity_id: string;
  quantity_target: number;
  quantity_current: number;
  issued_at: string;
  deadline: string;
  completed_at: string | null;
  status: string;
  reward_id: string | null;
}

export function useChallenges(token: string, retainCompleted = false) {
  const [current, setCurrent] = useState<ChallengeItem[]>([]);
  const [history, setHistory] = useState<PastChallengeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      apiFetch<{ items: ChallengeItem[]; empty_reason: string }>('/challenges/current', token),
      apiFetch<{ items: PastChallengeItem[]; total: number }>('/challenges/history', token),
    ])
      .then(([currentResp, historyResp]) => {
        setCurrent(previous => {
          if (!retainCompleted) return currentResp.items;
          const completed = new Map(historyResp.items
            .filter(item => item.status === 'выполнено')
            .map(item => [item.id, item]));
          const activeIds = new Set(currentResp.items.map(item => item.id));
          // Keep only tasks seen during this visit, never unrelated history.
          const retained = previous.flatMap(item => {
            if (activeIds.has(item.id)) return [];
            const done = completed.get(item.id) ?? (item.status === 'выполнено' ? item : null);
            return done ? [done] : [];
          });
          return [...currentResp.items, ...retained];
        });
        setHistory(historyResp.items);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, retainCompleted]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const clearCompleted = useCallback(() => {
    setCurrent(previous => previous.filter(item => item.status !== 'выполнено'));
  }, []);

  return { current, history, loading, error, refetch, clearCompleted };
}
