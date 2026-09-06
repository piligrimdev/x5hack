import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export type LeaderboardStatus = 'no_home_store' | 'ready';

export interface LeaderboardPeriod {
  year: number;
  month: number;
  timezone: 'Europe/Moscow';
}

export interface LeaderboardStore {
  id: string;
  name: string;
}

export interface LeaderboardMe {
  rank: number;
  savings_percent: number;
  beats_percent: number;
  top_percent?: number;
  in_top: boolean;
}

const TOP_BUCKETS = [1, 5, 10, 25, 50, 75, 100] as const;

export function topPercentBucket(rank: number, total: number): number {
  if (total <= 0) return 100;
  const raw = Math.max(1, Math.min(100, Math.ceil((rank / total) * 100)));
  return TOP_BUCKETS.find(bucket => raw <= bucket) ?? 100;
}

export interface LeaderboardEntry {
  rank: number;
  label: string;
  savings_percent: number;
  is_me: boolean;
}

export interface LeaderboardOut {
  status: LeaderboardStatus;
  period: LeaderboardPeriod;
  store: LeaderboardStore | null;
  participant_count: number;
  me: LeaderboardMe | null;
  entries: LeaderboardEntry[];
  solo: boolean;
}

export function useSavingsLeaderboard(token: string) {
  const [data, setData] = useState<LeaderboardOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const snapshot = await apiFetch<LeaderboardOut>('/leaderboard', token);
      if (snapshot.me) {
        const fromApi = snapshot.me.top_percent;
        snapshot.me.top_percent =
          typeof fromApi === 'number' && Number.isFinite(fromApi)
            ? fromApi
            : topPercentBucket(snapshot.me.rank, snapshot.participant_count);
      }
      setData(snapshot);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить рейтинг');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
