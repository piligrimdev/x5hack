import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface ChallengeTaskItem {
  id: string;
  label: string | null;
  criterion_type: string;
  criterion_entity_id: string;
  quantity_target: number;
  quantity_current: number;
}

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
  items?: ChallengeTaskItem[];
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

export function isBasketChallenge(challenge: Pick<ChallengeItem, 'mechanic'>): boolean {
  return challenge.mechanic.toLowerCase().includes('сумму корзины');
}

export function useChallenges(token: string, retainCompleted = false) {
  const [current, setCurrent] = useState<ChallengeItem[]>([]);
  const [history, setHistory] = useState<PastChallengeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [currentResp, historyResp] = await Promise.all([
        apiFetch<{ items: ChallengeItem[]; empty_reason: string }>('/challenges/current', token),
        apiFetch<{ items: PastChallengeItem[]; total: number }>('/challenges/history', token),
      ]);
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
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить задания');
    } finally {
      setLoading(false);
    }
  }, [token, retainCompleted]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const clearCompleted = useCallback(() => {
    setCurrent(previous => previous.filter(item => item.status !== 'выполнено'));
  }, []);

  return { current, history, loading, error, refetch, clearCompleted };
}
