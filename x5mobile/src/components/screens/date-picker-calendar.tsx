import { useMemo, useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { formatDay, startOfDay, startOfMonth } from '@/constants/economy-period';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

const WEEKDAYS = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
const MONTHS = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
];

function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

function mondayOffset(year: number, month: number): number {
  return (new Date(year, month, 1).getDay() + 6) % 7;
}

interface DatePickerCalendarProps {
  from: Date | null;
  to: Date | null;
  onChange: (from: Date, to: Date | null) => void;
  maxDate?: Date;
}

export function DatePickerCalendar({
  from,
  to,
  onChange,
  maxDate,
}: DatePickerCalendarProps) {
  const today = startOfDay(new Date());
  const limit = maxDate ? startOfDay(maxDate) : today;
  const [cursor, setCursor] = useState(() => startOfMonth(from ?? today));

  const cells = useMemo(() => {
    const year = cursor.getFullYear();
    const month = cursor.getMonth();
    const offset = mondayOffset(year, month);
    const last = new Date(year, month + 1, 0).getDate();
    const items: Array<{ key: string; date: Date | null }> = [];
    for (let i = 0; i < offset; i += 1) {
      items.push({ key: `pad-${i}`, date: null });
    }
    for (let day = 1; day <= last; day += 1) {
      items.push({ key: `${year}-${month}-${day}`, date: new Date(year, month, day) });
    }
    return items;
  }, [cursor]);

  function pick(date: Date) {
    if (date.getTime() > limit.getTime()) return;
    if (!from || (from && to)) {
      onChange(date, null);
      return;
    }
    onChange(from, date);
  }

  const rangeStart = from && to && from.getTime() > to.getTime() ? to : from;
  const rangeEnd = from && to && from.getTime() > to.getTime() ? from : to;

  return (
    <View style={styles.root}>
      <View style={styles.nav}>
        <TouchableOpacity
          style={styles.navBtn}
          onPress={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}
          activeOpacity={0.7}>
          <Text style={styles.navBtnText}>‹</Text>
        </TouchableOpacity>
        <Text style={styles.monthTitle}>
          {MONTHS[cursor.getMonth()]} {cursor.getFullYear()}
        </Text>
        <TouchableOpacity
          style={styles.navBtn}
          onPress={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}
          activeOpacity={0.7}>
          <Text style={styles.navBtnText}>›</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.weekRow}>
        {WEEKDAYS.map((day) => (
          <Text key={day} style={styles.weekday}>{day}</Text>
        ))}
      </View>

      <View style={styles.grid}>
        {cells.map((cell) => {
          if (!cell.date) {
            return <View key={cell.key} style={styles.cell} />;
          }
          const date = cell.date;
          const disabled = date.getTime() > limit.getTime();
          const isStart = Boolean(rangeStart && sameDay(date, rangeStart));
          const isEnd = Boolean(rangeEnd && sameDay(date, rangeEnd));
          const inRange = Boolean(
            rangeStart
            && rangeEnd
            && date.getTime() > rangeStart.getTime()
            && date.getTime() < rangeEnd.getTime(),
          );
          const isToday = sameDay(date, today);
          return (
            <TouchableOpacity
              key={cell.key}
              style={[
                styles.cell,
                inRange && styles.cellInRange,
                (isStart || isEnd) && styles.cellSelected,
              ]}
              onPress={() => pick(date)}
              disabled={disabled}
              activeOpacity={0.75}>
              <Text
                style={[
                  styles.cellText,
                  disabled && styles.cellDisabled,
                  isToday && styles.cellToday,
                  (isStart || isEnd) && styles.cellSelectedText,
                ]}>
                {date.getDate()}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      <Text style={styles.hint}>
        {!from
          ? 'Выберите дату начала'
          : !to
            ? `С ${formatDay(from)} — выберите дату конца`
            : `С ${formatDay(rangeStart ?? from)} по ${formatDay(rangeEnd ?? to)}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 12,
    gap: 8,
  },
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  navBtn: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  navBtnText: { color: DARK_GREEN, fontSize: 26, fontWeight: '700', lineHeight: 28 },
  monthTitle: { color: DARK_GREEN, fontSize: 16, fontWeight: '800', textTransform: 'capitalize' },
  weekRow: { flexDirection: 'row' },
  weekday: {
    width: `${100 / 7}%`,
    textAlign: 'center',
    color: MUTED,
    fontSize: 11,
    fontWeight: '700',
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  cell: {
    width: `${100 / 7}%`,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cellInRange: { backgroundColor: '#E8F6EC' },
  cellSelected: { backgroundColor: GREEN, borderRadius: 19 },
  cellText: { color: TEXT, fontSize: 14, fontWeight: '700' },
  cellDisabled: { color: '#C8CBC8' },
  cellToday: { color: GREEN },
  cellSelectedText: { color: '#FFFFFF' },
  hint: { color: MUTED, fontSize: 12, textAlign: 'center' },
});
