import { useCallback, useEffect, useState } from 'react';

import { apiListAvailableDiscounts, type UserDiscountOut } from '@/api/client';

export function useDiscounts(token: string) {
  const [items, setItems] = useState<UserDiscountOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiListAvailableDiscounts(token);
      setItems(data.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить скидки');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { items, loading, error, refetch };
}
