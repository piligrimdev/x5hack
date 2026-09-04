import { useEffect, useState } from 'react';

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

export function useChallenges(token: string) {
  const [current, setCurrent] = useState<ChallengeItem[]>([]);
  const [history, setHistory] = useState<PastChallengeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    Promise.all([
      apiFetch<{ items: ChallengeItem[]; empty_reason: string }>('/challenges/current', token),
      apiFetch<{ items: PastChallengeItem[]; total: number }>('/challenges/history', token),
    ])
      .then(([currentResp, historyResp]) => {
        setCurrent(currentResp.items);
        setHistory(historyResp.items);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  return { current, history, loading, error };
}
