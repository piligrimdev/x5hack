export type PeriodKind = 'day' | 'week' | 'month' | 'custom';
export type PeriodShift = 'current' | 'previous';

export interface EconomyRange {
  from: Date;
  toInclusive: Date;
  label: string;
}

const RU_MONTHS = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
];

export function startOfDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

export function addDays(value: Date, days: number): Date {
  const next = startOfDay(value);
  next.setDate(next.getDate() + days);
  return next;
}

export function startOfWeek(value: Date): Date {
  const day = startOfDay(value);
  const mondayOffset = (day.getDay() + 6) % 7;
  day.setDate(day.getDate() - mondayOffset);
  return day;
}

export function startOfMonth(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

export function toQueryDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function formatDay(value: Date): string {
  return value.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

export function resolvePresetRange(kind: Exclude<PeriodKind, 'custom'>, shift: PeriodShift, now = new Date()): EconomyRange {
  if (kind === 'day') {
    const from = addDays(startOfDay(now), shift === 'previous' ? -1 : 0);
    return {
      from,
      toInclusive: from,
      label: shift === 'previous' ? 'вчера' : 'сегодня',
    };
  }
  if (kind === 'week') {
    const from = addDays(startOfWeek(now), shift === 'previous' ? -7 : 0);
    const toInclusive = addDays(from, 6);
    return {
      from,
      toInclusive,
      label: shift === 'previous' ? 'прошлая неделя' : 'эта неделя',
    };
  }
  const from = startOfMonth(now);
  if (shift === 'previous') {
    const prev = new Date(from.getFullYear(), from.getMonth() - 1, 1);
    const last = new Date(from.getFullYear(), from.getMonth(), 0);
    return {
      from: prev,
      toInclusive: last,
      label: `за ${RU_MONTHS[prev.getMonth()]}`,
    };
  }
  const last = new Date(from.getFullYear(), from.getMonth() + 1, 0);
  return {
    from,
    toInclusive: last,
    label: `за ${RU_MONTHS[from.getMonth()]}`,
  };
}

export function resolveCustomRange(from: Date, toInclusive: Date): EconomyRange {
  const start = startOfDay(from);
  const end = startOfDay(toInclusive);
  const ordered = end < start ? { from: end, toInclusive: start } : { from: start, toInclusive: end };
  const sameDay = ordered.from.getTime() === ordered.toInclusive.getTime();
  return {
    ...ordered,
    label: sameDay
      ? formatDay(ordered.from)
      : `с ${formatDay(ordered.from)} по ${formatDay(ordered.toInclusive)}`,
  };
}

export function parseDateInput(raw: string): Date | null {
  const trimmed = raw.trim();
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmed);
  if (iso) {
    const date = new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const ru = /^(\d{1,2})[.](\d{1,2})[.](\d{4})$/.exec(trimmed);
  if (ru) {
    const date = new Date(Number(ru[3]), Number(ru[2]) - 1, Number(ru[1]));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
}
