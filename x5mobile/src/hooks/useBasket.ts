import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useRef, useState } from 'react';

import { apiFetch } from '@/api/client';

const STORAGE_KEY = '@x5hack/weeklyBasket';
const ASSISTANT_POLL_INTERVAL_MS = 800;
const ASSISTANT_POLL_TIMEOUT_MS = 15_000;

export interface BasketItem {
  product_id: string;
  name: string;
  quantity: number;
  price: number;
}

interface SuggestedBasketResponse {
  items: BasketItem[];
}

interface AssistantResponse {
  items: BasketItem[];
  applied: boolean;
  message: string | null;
}

interface AssistantEnqueuedResponse {
  task_id: string;
  status: 'pending';
}

interface AssistantTaskResultResponse {
  status: 'pending' | 'complete' | 'failed';
  result?: AssistantResponse;
}

interface CheckoutResponse {
  total_saved: number;
}

export interface BasketPreviewItem {
  product_id: string;
  product_name: string;
  quantity: number;
  base_price: number;
  paid_price: number;
  discount_id: string | null;
  discounted_amount: number;
}

export interface BasketPreviewCashback {
  points_available: number;
  points_to_apply: number;
  cashback_rub: number;
  total_paid_rub: number;
  points_balance_after: number;
  points_capped_by: 'none' | 'balance' | 'receipt_total';
  rate_points_per_rub: number;
}

export interface BasketPreview {
  items: BasketPreviewItem[];
  total_base: number;
  total_paid: number;
  total_saved: number;
  cashback: BasketPreviewCashback | null;
}

async function pollAssistantResult(
  taskId: string,
  token: string,
  signal: AbortSignal,
): Promise<AssistantResponse> {
  const deadline = Date.now() + ASSISTANT_POLL_TIMEOUT_MS;
  while (!signal.aborted && Date.now() < deadline) {
    await new Promise<void>((resolve) => setTimeout(resolve, ASSISTANT_POLL_INTERVAL_MS));
    if (signal.aborted) break;

    const poll = await apiFetch<AssistantTaskResultResponse>(
      `/basket/assistant/${taskId}`,
      token,
    );
    if (poll.status === 'complete' && poll.result) return poll.result;
    if (poll.status === 'failed') throw new Error('Не получилось обработать запрос, попробуй ещё раз');
  }
  throw new Error('Ассистент не ответил вовремя, попробуй ещё раз');
}

export function useBasket(token: string | null, onOrderPlaced?: () => void) {
  const [items, setItems] = useState<BasketItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<BasketPreview | null>(null);
  const [spendPoints, setSpendPoints] = useState(false);
  const [hasCollected, setHasCollected] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const [storageKey, setStorageKey] = useState<string | null>(null);
  const busy = useRef(false);
  // Share the login request across StrictMode effect replays.
  const loginRequest = useRef<{ token: string; result: Promise<{ data?: SuggestedBasketResponse; error?: unknown }> } | null>(null);

  useEffect(() => {
    let active = true;
    setHydrated(false);
    setLoading(true);
    busy.current = true;
    setStorageKey(null);
    setItems([]);
    setHasCollected(false);
    setSpendPoints(false);
    setMessage(null);
    (async () => {
      try {
        if (!token) return;
        if (loginRequest.current?.token !== token) {
          loginRequest.current = {
            token,
            result: apiFetch<SuggestedBasketResponse>('/basket/suggested', token)
              .then(data => ({ data }), error => ({ error })),
          };
        }
        const generation = loginRequest.current.result;
        const { user_id } = await apiFetch<{ user_id: string }>('/me', token);
        const key = `${STORAGE_KEY}/${user_id}`;
        // The old shared key has no owner, so never import it into an account.
        const raw = await AsyncStorage.getItem(key).catch(() => null);
        if (!active) return;
        setStorageKey(key);
        if (raw !== null) {
          const parsed = (() => { try { return JSON.parse(raw); } catch { return null; } })();
          if (Array.isArray(parsed)) {
            setItems(parsed);
            setHasCollected(true);
          }
        }
        setHydrated(true);
        const result = await generation;
        if (!active) return;
        if (!result.data) {
          setMessage('Аппи не удалось собрать корзину. Попробуйте собрать ещё раз.');
          return;
        }
        await AsyncStorage.setItem(key, JSON.stringify(result.data.items)).catch(() => {});
        if (!active) return;
        setItems(result.data.items);
        setHasCollected(true);
      } catch {
        if (active) setMessage('Не удалось загрузить корзину. Откройте приложение ещё раз.');
      } finally {
        if (active) {
          setHydrated(true);
          setLoading(false);
          busy.current = false;
        }
      }
    })();
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    let active = true;
    setPreview(null);
    if (!token || items.length === 0) return;
    apiFetch<BasketPreview>('/basket/preview', token, {
      method: 'POST',
      body: JSON.stringify({
        items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
        points_to_spend: spendPoints ? 'all' : null,
      }),
    })
      .then((result) => { if (active) setPreview(result); })
      .catch(() => { if (active) setPreview(null); });
    return () => { active = false; };
  }, [token, items, spendPoints]);

  async function collectWeeklyBasket() {
    if (!token || !hydrated || !storageKey || busy.current) return;
    busy.current = true;
    setLoading(true);
    try {
      const data = await apiFetch<SuggestedBasketResponse>('/basket/suggested', token);
      await AsyncStorage.setItem(storageKey, JSON.stringify(data.items)).catch(() => {});
      setMessage(null);
      setItems(data.items);
      setHasCollected(true);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка сбора корзины');
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }

  async function sendInstruction(instruction: string) {
    if (!token || !hydrated || !storageKey || !instruction.trim() || busy.current) return;
    busy.current = true;
    setLoading(true);
    const abortController = new AbortController();
    try {
      // POST returns 202 with task_id immediately
      const enqueued = await apiFetch<AssistantEnqueuedResponse>('/basket/assistant', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          instruction,
        }),
      });
      // Poll until complete or timeout
      const res = await pollAssistantResult(enqueued.task_id, token, abortController.signal);
      await AsyncStorage.setItem(storageKey, JSON.stringify(res.items)).catch(() => {});
      setHasCollected(true);
      setItems(res.items);
      setMessage(res.message);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка запроса');
    } finally {
      abortController.abort();
      busy.current = false;
      setLoading(false);
    }
  }

  async function checkout() {
    if (!token || !hydrated || !storageKey || items.length === 0 || busy.current) return false;
    busy.current = true;
    setLoading(true);
    try {
      const res = await apiFetch<CheckoutResponse>('/basket/checkout', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          points_to_spend: spendPoints ? 'all' : null,
        }),
      });
      await AsyncStorage.removeItem(storageKey).catch(() => {});
      setItems([]);
      setHasCollected(false);
      setPreview(null);
      setSpendPoints(false);
      setMessage(`Заказ оформлен! Сэкономлено ${Math.round(res.total_saved)} ₽`);
      return true;
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка оформления заказа');
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }

  return {
    items,
    loading,
    message,
    sendInstruction,
    checkout,
    preview,
    spendPoints,
    setSpendPoints,
    hasCollected,
    hydrated,
    collectWeeklyBasket,
  };
}

export type BasketState = ReturnType<typeof useBasket>;
