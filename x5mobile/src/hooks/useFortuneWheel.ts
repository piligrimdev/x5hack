import { useCallback, useEffect, useState } from 'react';

export type FortunePrizeType = 'cashback' | 'discount' | 'gift';

export interface FortunePrize {
  id: string;
  type: FortunePrizeType;
  title: string;
  subtitle: string;
  shortLabel: string;
  emoji: string;
  color: string;
  textColor: string;
  weight: number;
}

export interface FortuneWin {
  id: string;
  prize: FortunePrize;
  wonAt: string;
}

export interface FortuneWheelSnapshot {
  prizes: FortunePrize[];
  spinsLeft: number;
  spinsPerDay: number;
  nextResetAt: string;
  history: FortuneWin[];
}

const PRIZES: FortunePrize[] = [
  {
    id: 'cashback-50',
    type: 'cashback',
    title: '50 баллов',
    subtitle: 'Зачислим на карту Х5 Клуба',
    shortLabel: '50 б.',
    emoji: '💰',
    color: '#FF6D00',
    textColor: '#FFFFFF',
    weight: 24,
  },
  {
    id: 'discount-fruit',
    type: 'discount',
    title: 'Скидка 10% на фрукты',
    subtitle: 'Действует 3 дня на весь отдел',
    shortLabel: '−10%',
    emoji: '🍎',
    color: '#1B5E35',
    textColor: '#FFFFFF',
    weight: 16,
  },
  {
    id: 'gift-banana',
    type: 'gift',
    title: 'Бесплатный банан',
    subtitle: 'Подарок в следующем заказе',
    shortLabel: 'подарок',
    emoji: '🍌',
    color: '#F5C518',
    textColor: '#17171A',
    weight: 12,
  },
  {
    id: 'cashback-100',
    type: 'cashback',
    title: '100 баллов',
    subtitle: 'Зачислим на карту Х5 Клуба',
    shortLabel: '100 б.',
    emoji: '💎',
    color: '#25A244',
    textColor: '#FFFFFF',
    weight: 14,
  },
  {
    id: 'discount-dairy',
    type: 'discount',
    title: 'Скидка 15% на молочку',
    subtitle: 'Действует 5 дней на молочные продукты',
    shortLabel: '−15%',
    emoji: '🥛',
    color: '#E85D04',
    textColor: '#FFFFFF',
    weight: 12,
  },
  {
    id: 'gift-spin',
    type: 'gift',
    title: 'Ещё одна крутка',
    subtitle: 'Аппи дарит дополнительный шанс',
    shortLabel: '+крутка',
    emoji: '🎁',
    color: '#7B2D8E',
    textColor: '#FFFFFF',
    weight: 8,
  },
  {
    id: 'discount-order',
    type: 'discount',
    title: 'Скидка 5% на заказ',
    subtitle: 'Сработает при следующем оформлении',
    shortLabel: '−5%',
    emoji: '🛒',
    color: '#2A9D8F',
    textColor: '#FFFFFF',
    weight: 10,
  },
  {
    id: 'cashback-200',
    type: 'cashback',
    title: '200 баллов',
    subtitle: 'Редкий приз — крупное начисление',
    shortLabel: '200 б.',
    emoji: '🏆',
    color: '#C99A3E',
    textColor: '#17171A',
    weight: 4,
  },
];

function tomorrowMidnightIso(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function yesterdayIso(hours = 19, minutes = 12): string {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  d.setHours(hours, minutes, 0, 0);
  return d.toISOString();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function pickWeighted(prizes: FortunePrize[]): FortunePrize {
  const total = prizes.reduce((sum, prize) => sum + prize.weight, 0);
  let cursor = Math.random() * total;
  for (const prize of prizes) {
    cursor -= prize.weight;
    if (cursor <= 0) return prize;
  }
  return prizes[prizes.length - 1];
}

function cloneSnapshot(state: FortuneWheelSnapshot): FortuneWheelSnapshot {
  return {
    ...state,
    prizes: state.prizes,
    history: [...state.history],
  };
}

/** In-memory stand-in for GET/POST /fortune-wheel — swap for apiFetch later. */
const store: FortuneWheelSnapshot = {
  prizes: PRIZES,
  spinsLeft: 3,
  spinsPerDay: 3,
  nextResetAt: tomorrowMidnightIso(),
  history: [
    {
      id: 'win-seed-1',
      prize: PRIZES[0],
      wonAt: yesterdayIso(20, 41),
    },
    {
      id: 'win-seed-2',
      prize: PRIZES[1],
      wonAt: yesterdayIso(11, 8),
    },
  ],
};

export function useFortuneWheel(_token: string) {
  const [snapshot, setSnapshot] = useState<FortuneWheelSnapshot>(() => cloneSnapshot(store));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(false);
    setError(null);
    setSnapshot(cloneSnapshot(store));
  }, [_token]);

  const spin = useCallback(async (): Promise<FortunePrize> => {
    if (store.spinsLeft <= 0) {
      throw new Error('Крутки закончились');
    }
    await delay(160);
    const prize = pickWeighted(store.prizes);
    store.spinsLeft -= 1;
    if (prize.id === 'gift-spin') {
      store.spinsLeft += 1;
    }
    store.history = [
      { id: `win-${Date.now()}`, prize, wonAt: new Date().toISOString() },
      ...store.history,
    ];
    setSnapshot(cloneSnapshot(store));
    return prize;
  }, []);

  return { snapshot, loading, error, spin };
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
  if (type === 'cashback') return 'Кешбэк';
  if (type === 'discount') return 'Скидка';
  return 'Подарок';
}
