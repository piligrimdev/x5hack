import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiFetch, apiListCouponTransactions, type CouponTxOut } from '@/api/client';

export type FortunePrizeType = 'cashback' | 'gift';

export interface WheelGift {
  criterion_type: 'product' | 'category';
  criterion_entity_id: string;
  quantity: number;
}

export interface WheelSector {
  code: string;
  label: string;
  description: string;
  prize_type: FortunePrizeType;
  probability_percent: number;
  cashback_rub: number | null;
  gift: WheelGift | null;
}

export interface WheelState {
  coupons: number;
  can_spin: boolean;
  sectors: WheelSector[];
}

export interface SpinResult {
  spin_id: string;
  sector_code: string;
  prize_type: FortunePrizeType;
  prize_label: string;
  cashback_rub: number | null;
  points_awarded: number | null;
  gift_reward_id: string | null;
  coupons_after: number;
  created_at: string;
}

export interface SpinHistoryItem {
  id: string;
  sector_code: string;
  prize_type: FortunePrizeType;
  prize_label: string;
  cashback_rub: number | null;
  gift_reward_id: string | null;
  gift_status: 'active' | 'used' | 'expired' | null;
  coupons_spent: number;
  created_at: string;
}

export interface FortunePrize {
  id: string;
  type: FortunePrizeType;
  title: string;
  subtitle: string;
  shortLabel: string;
  emoji: string;
  color: string;
  textColor: string;
}

const FLESH_LIGHT = '#FFB347';
const FLESH_DARK = '#F56A00';

function mapSector(sector: WheelSector, index: number): FortunePrize {
  const light = index % 2 === 0;
  const isGift = sector.prize_type === 'gift';
  return {
    id: sector.code,
    type: sector.prize_type,
    title: sector.label,
    subtitle: sector.description,
    shortLabel: isGift
      ? 'подарок'
      : sector.cashback_rub != null
        ? `${sector.cashback_rub} ₽`
        : sector.label,
    emoji: isGift ? '🎁' : '💰',
    color: light ? FLESH_LIGHT : FLESH_DARK,
    textColor: light ? '#5C2E00' : '#FFFFFF',
  };
}

export function describeWheelError(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  if (message.includes('INSUFFICIENT_COUPONS') || message.startsWith('409')) {
    return 'Не хватает купонов для крутки';
  }
  if (message.startsWith('503')) {
    return 'Призы временно недоступны';
  }
  return error instanceof Error ? error.message : 'Не удалось загрузить колесо';
}

export function useFortuneWheel(token: string) {
  const [state, setState] = useState<WheelState | null>(null);
  const [history, setHistory] = useState<SpinHistoryItem[]>([]);
  const [couponTx, setCouponTx] = useState<CouponTxOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [wheel, spins, coupons] = await Promise.all([
        apiFetch<WheelState>('/wheel', token),
        apiFetch<{ items: SpinHistoryItem[] }>('/wheel/spins?limit=8&offset=0', token),
        apiListCouponTransactions(token, 20, 0),
      ]);
      setState(wheel);
      setHistory(spins.items);
      setCouponTx(coupons.items);
    } catch (e: unknown) {
      setError(describeWheelError(e));
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const prizes = useMemo(
    () => (state?.sectors ?? []).map(mapSector),
    [state?.sectors],
  );

  const spin = useCallback(async (): Promise<{ prize: FortunePrize; result: SpinResult; targetIndex: number }> => {
    if (!state?.can_spin) {
      throw new Error('Не хватает купонов для крутки');
    }
    setError(null);
    try {
      const result = await apiFetch<SpinResult>('/wheel/spin', token, {
        method: 'POST',
        body: '{}',
      });
      setState((prev) => (
        prev
          ? { ...prev, coupons: result.coupons_after, can_spin: result.coupons_after > 0 }
          : prev
      ));
      setHistory((prev) => [
        {
          id: result.spin_id,
          sector_code: result.sector_code,
          prize_type: result.prize_type,
          prize_label: result.prize_label,
          cashback_rub: result.cashback_rub,
          gift_reward_id: result.gift_reward_id,
          gift_status: result.prize_type === 'gift' ? 'active' : null,
          coupons_spent: 1,
          created_at: result.created_at,
        },
        ...prev,
      ]);
      setCouponTx((prev) => [
        {
          id: `${result.spin_id}-coupon`,
          type: 'spin',
          amount: -1,
          related_task_id: null,
          related_spin_id: result.spin_id,
          related_referral_link_id: null,
          related_receipt_id: null,
          week_start: null,
          created_at: result.created_at,
        },
        ...prev,
      ]);
      const targetIndex = Math.max(
        0,
        prizes.findIndex((prize) => prize.id === result.sector_code),
      );
      const prize = prizes[targetIndex];
      return { prize, result, targetIndex };
    } catch (e: unknown) {
      const message = describeWheelError(e);
      setError(message);
      throw new Error(message);
    }
  }, [prizes, state?.can_spin, token]);

  return { state, prizes, history, couponTx, loading, error, spin, refetch: load };
}

export function formatWinTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const time = date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  if (sameDay) return `Сегодня, ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    date.getFullYear() === yesterday.getFullYear() &&
    date.getMonth() === yesterday.getMonth() &&
    date.getDate() === yesterday.getDate();
  if (isYesterday) return `Вчера, ${time}`;
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

export function prizeTypeLabel(type: FortunePrizeType): string {
  return type === 'cashback' ? 'Кешбэк' : 'Подарок';
}
