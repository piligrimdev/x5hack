import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

const STORAGE_KEY = '@x5hack/weeklyBasket';

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

export function useBasket(token: string | null, onOrderPlaced?: () => void) {
  const [items, setItems] = useState<BasketItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<BasketPreview | null>(null);
  const [spendPoints, setSpendPoints] = useState(false);
  const [hasCollected, setHasCollected] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        if (raw !== null) {
          setItems(JSON.parse(raw));
          setHasCollected(true);
        }
      } catch {
        // corrupt or unavailable storage — start with an empty, uncollected basket
      } finally {
        setHydrated(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!hydrated || !hasCollected) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items)).catch(() => {});
  }, [items, hasCollected, hydrated]);

  useEffect(() => {
    if (!token || items.length === 0) {
      setPreview(null);
      return;
    }
    apiFetch<BasketPreview>('/basket/preview', token, {
      method: 'POST',
      body: JSON.stringify({
        items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
        points_to_spend: spendPoints ? 'all' : null,
      }),
    })
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [token, items, spendPoints]);

  async function collectWeeklyBasket() {
    if (!token) return;
    setLoading(true);
    try {
      const data = await apiFetch<SuggestedBasketResponse>('/basket/suggested', token);
      setItems(data.items);
      setHasCollected(true);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка сбора корзины');
    } finally {
      setLoading(false);
    }
  }

  async function sendInstruction(instruction: string) {
    if (!token || !instruction.trim()) return;
    setLoading(true);
    try {
      const res = await apiFetch<AssistantResponse>('/basket/assistant', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          instruction,
        }),
      });
      setItems(res.items);
      setMessage(res.applied ? null : res.message);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка запроса');
    } finally {
      setLoading(false);
    }
  }

  async function checkout() {
    if (!token || items.length === 0) return;
    setLoading(true);
    try {
      const res = await apiFetch<CheckoutResponse>('/basket/checkout', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          points_to_spend: spendPoints ? 'all' : null,
        }),
      });
      setItems([]);
      setHasCollected(false);
      setPreview(null);
      setSpendPoints(false);
      AsyncStorage.removeItem(STORAGE_KEY).catch(() => {});
      setMessage(`Заказ оформлен! Сэкономлено ${Math.round(res.total_saved)} ₽`);
      onOrderPlaced?.();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка оформления заказа');
    } finally {
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
