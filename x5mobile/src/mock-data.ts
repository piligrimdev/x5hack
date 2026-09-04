export interface Task {
  id: number;
  title: string;
  sub: string;
  progress: number;
  total: number;
  done: boolean;
  reward: string;
}

export interface HistoryItem {
  id: number;
  place: string;
  dateLabel: string;
  items: number;
  sum: string;
  saved: string;
}

export interface LeaderboardEntry {
  rank: number;
  initial: string;
  name: string;
  saved: string;
  me?: boolean;
}

export interface Savings {
  paid: number;
  withoutDiscount: number;
}

export interface User {
  points: number;
  level: string;
  cashback: string;
  categoryBonus: string;
}

export interface MockData {
  tasks: Task[];
  history: HistoryItem[];
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  user: User;
}

const mockData: MockData = {
  tasks: [
    { id: 1, title: 'Купи молоко 3 раза', sub: 'Осталось 1 покупка', progress: 2, total: 3, done: false, reward: 'Скидка 15% на молочные продукты — 7 дней' },
    { id: 2, title: 'Купи хлеб 2 раза', sub: 'Выполнено', progress: 2, total: 2, done: true, reward: 'Скидка 10% на хлеб — активна до 10.09' },
    { id: 3, title: 'Сделай покупку от 1 500 ₽', sub: 'Собрано 980 из 1 500 ₽', progress: 980, total: 1500, done: false, reward: 'Кешбэк 5% на следующую покупку' },
    { id: 4, title: 'Купи 5 разных овощей', sub: 'Куплено 3 из 5', progress: 3, total: 5, done: false, reward: 'Скидка 20% на овощи и фрукты — 3 дня' },
    { id: 5, title: '3 покупки за неделю', sub: 'Выполнено', progress: 3, total: 3, done: true, reward: '+50 бонусных баллов' },
  ],
  history: [
    { id: 1, place: 'Магазин на Ленина, 12', dateLabel: 'Сегодня, 18:32', items: 8, sum: '1 240 ₽', saved: '210' },
    { id: 2, place: 'Магазин у дома', dateLabel: 'Вчера, 09:15', items: 3, sum: '560 ₽', saved: '80' },
    { id: 3, place: 'Магазин на Ленина, 12', dateLabel: '28 августа, 20:05', items: 12, sum: '2 130 ₽', saved: '340' },
    { id: 4, place: 'Магазин у дома', dateLabel: '26 августа, 12:40', items: 5, sum: '894 ₽', saved: '95' },
    { id: 5, place: 'Магазин на Ленина, 12', dateLabel: '22 августа, 19:10', items: 6, sum: '1 470 ₽', saved: '135' },
  ],
  leaderboard: [
    { rank: 1, initial: 'А', name: 'Анна К.', saved: '1 240' },
    { rank: 2, initial: 'М', name: 'Максим П.', saved: '980' },
    { rank: 3, initial: 'Вы', name: 'Вы', saved: '460', me: true },
    { rank: 4, initial: 'Д', name: 'Дарья С.', saved: '410' },
    { rank: 5, initial: 'И', name: 'Игорь Т.', saved: '350' },
  ],
  savings: { paid: 2740, withoutDiscount: 3200 },
  user: { points: 128, level: 'Золотой уровень', cashback: '1%', categoryBonus: '×3' },
};

export function useMockData(): MockData {
  return mockData;
}

export default mockData;
