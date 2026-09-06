import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface Vibe {
  id: string;
  name: string;
  description: string;
  llm_context: string;
}

export function useVibes(token: string) {
  const [vibes, setVibes] = useState<Vibe[]>([]);
  const [selectedVibeId, setSelectedVibeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [available, me] = await Promise.all([
        apiFetch<Vibe[]>('/vibes', token),
        apiFetch<{ vibe_id: string | null }>('/users/me/vibe', token),
      ]);
      setVibes(available);
      setSelectedVibeId(me.vibe_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить вайбы');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const saveVibe = useCallback(async (vibeId: string | null) => {
    setSaving(true);
    setError(null);
    try {
      await apiFetch<{ vibe_id: string | null }>('/users/me/vibe', token, {
        method: 'PUT',
        body: JSON.stringify({ vibe_id: vibeId }),
      });
      setSelectedVibeId(vibeId);
      return true;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить вайб');
      return false;
    } finally {
      setSaving(false);
    }
  }, [token]);

  return { vibes, selectedVibeId, loading, saving, error, saveVibe, refetch: load };
}
