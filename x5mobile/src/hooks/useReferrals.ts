import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  apiIssueReferral,
  apiListReferrals,
  type ReferralOut,
} from '@/api/client';

export function useReferrals(token: string) {
  const [items, setItems] = useState<ReferralOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [issuing, setIssuing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiListReferrals(token);
      setItems(data.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить приглашения');
    } finally {
      setLoading(false);
    }
  }, [token]);

  const issue = useCallback(async () => {
    setIssuing(true);
    setError(null);
    try {
      const created = await apiIssueReferral(token);
      setItems(prev => [created, ...prev.filter(item => item.id !== created.id)]);
      return created;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось создать код');
      return null;
    } finally {
      setIssuing(false);
    }
  }, [token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const latest = useMemo(
    () => items.find(item => item.status === 'issued') ?? items[0] ?? null,
    [items],
  );

  return { items, latest, loading, issuing, error, issue, refetch };
}
