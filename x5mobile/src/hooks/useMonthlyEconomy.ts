import { useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';
import { receiptSavedRub } from '@/hooks/useReceipts';

interface ReceiptSlim {
  purchase_date: string;
  total_saved: number;
  total_base: number;
  discount_saved_rub?: number;
  cashback_applied_rub?: number;
}

export interface MonthData {
  key: string;   // "2026-09"
  label: string; // "сен"
  saved: number;
}

export interface MonthlyEconomy {
  months: MonthData[];
  currentMonthSaved: number;
  currentMonthCashbackRub: number;
  currentMonthBase: number;
  consecutiveGrowthMonths: number;
}

const SHORT_MONTHS = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];

function monthKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

export function useMonthlyEconomy(token: string) {
  const [data, setData] = useState<MonthlyEconomy | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    apiFetch<{ items: ReceiptSlim[] }>('/receipts?size=200', token)
      .then(resp => {
        const bySaved = new Map<string, number>();
        const byCashback = new Map<string, number>();
        const byBase = new Map<string, number>();
        for (const r of resp.items) {
          const key = monthKey(new Date(r.purchase_date));
          bySaved.set(key, (bySaved.get(key) ?? 0) + receiptSavedRub(r));
          byCashback.set(key, (byCashback.get(key) ?? 0) + (r.cashback_applied_rub ?? 0));
          byBase.set(key, (byBase.get(key) ?? 0) + (r.total_base ?? 0));
        }

        const now = new Date();
        const months: MonthData[] = [];
        for (let i = 3; i >= 0; i--) {
          const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
          const key = monthKey(d);
          months.push({ key, label: SHORT_MONTHS[d.getMonth()], saved: Math.round(bySaved.get(key) ?? 0) });
        }

        const currentKey = monthKey(now);
        const currentMonthSaved = Math.round(bySaved.get(currentKey) ?? 0);
        const currentMonthCashbackRub = Math.round(byCashback.get(currentKey) ?? 0);
        const currentMonthBase = Math.round(byBase.get(currentKey) ?? 0);

        let streak = 0;
        for (let i = months.length - 1; i > 0; i--) {
          if (months[i].saved > months[i - 1].saved) streak++;
          else break;
        }

        setData({
          months,
          currentMonthSaved,
          currentMonthCashbackRub,
          currentMonthBase,
          consecutiveGrowthMonths: streak,
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  return { monthlyEconomy: data, loading };
}
