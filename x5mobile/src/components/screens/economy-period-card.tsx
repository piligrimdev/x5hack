import { useMemo, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { DatePickerCalendar } from '@/components/screens/date-picker-calendar';
import {
  type EconomyRange,
  type PeriodKind,
  type PeriodShift,
  resolveCustomRange,
  resolvePresetRange,
  toQueryDate,
} from '@/constants/economy-period';
import { useEconomy } from '@/hooks/useEconomy';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

const KINDS: { id: PeriodKind; label: string }[] = [
  { id: 'day', label: 'День' },
  { id: 'week', label: 'Неделя' },
  { id: 'month', label: 'Месяц' },
  { id: 'custom', label: 'Период' },
];

function formatRub(value: number): string {
  return value.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

interface EconomyPeriodCardProps {
  token: string;
}

export function EconomyPeriodCard({ token }: EconomyPeriodCardProps) {
  const [kind, setKind] = useState<PeriodKind>('month');
  const [shift, setShift] = useState<PeriodShift>('current');
  const [custom, setCustom] = useState<EconomyRange | null>(null);
  const [pickFrom, setPickFrom] = useState<Date | null>(null);
  const [pickTo, setPickTo] = useState<Date | null>(null);

  const range = useMemo(() => {
    if (kind === 'custom') {
      return custom ?? resolvePresetRange('month', 'current');
    }
    return resolvePresetRange(kind, shift);
  }, [kind, shift, custom]);

  const query = useMemo(
    () => ({ from: toQueryDate(range.from), to: toQueryDate(range.toInclusive) }),
    [range.from, range.toInclusive],
  );
  const { economy, loading } = useEconomy(token, query);
  const totalSaved = economy?.total_saved ?? 0;
  const totalPaid = economy?.total_paid ?? 0;
  const withoutDiscount = totalPaid + totalSaved;
  const savedPct = withoutDiscount > 0 ? Math.round((totalSaved / withoutDiscount) * 100) : 0;

  function handleCalendarChange(from: Date, to: Date | null) {
    setPickFrom(from);
    setPickTo(to);
    setCustom(resolveCustomRange(from, to ?? from));
  }

  return (
    <View style={styles.card}>
      <Text style={styles.eyebrow}>Ваша экономия</Text>
      <View style={styles.chips}>
        {KINDS.map((item) => (
          <TouchableOpacity
            key={item.id}
            style={[styles.chip, kind === item.id && styles.chipActive]}
            onPress={() => {
              setKind(item.id);
              if (item.id === 'custom' && !pickFrom) {
                const preset = resolvePresetRange('month', 'current');
                setPickFrom(preset.from);
                setPickTo(preset.toInclusive);
                setCustom(preset);
              }
            }}
            activeOpacity={0.8}>
            <Text style={[styles.chipText, kind === item.id && styles.chipTextActive]}>{item.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {kind === 'custom' ? (
        <DatePickerCalendar
          from={pickFrom}
          to={pickTo}
          onChange={handleCalendarChange}
        />
      ) : (
        <View style={styles.chips}>
          <TouchableOpacity
            style={[styles.chip, shift === 'current' && styles.chipActive]}
            onPress={() => setShift('current')}
            activeOpacity={0.8}>
            <Text style={[styles.chipText, shift === 'current' && styles.chipTextActive]}>
              {kind === 'day' ? 'Сегодня' : kind === 'week' ? 'Эта неделя' : 'Этот месяц'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.chip, shift === 'previous' && styles.chipActive]}
            onPress={() => setShift('previous')}
            activeOpacity={0.8}>
            <Text style={[styles.chipText, shift === 'previous' && styles.chipTextActive]}>
              {kind === 'day' ? 'Вчера' : kind === 'week' ? 'Прошлая неделя' : 'Прошлый месяц'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {loading ? (
        <ActivityIndicator color={GREEN} style={styles.loader} />
      ) : (
        <>
          <Text style={styles.amount}>−{formatRub(totalSaved)} ₽</Text>
          <Text style={styles.period}>{range.label}</Text>
          {savedPct > 0 ? (
            <Text style={styles.share}>{savedPct}% от покупок за этот период</Text>
          ) : (
            <Text style={styles.share}>
              {economy?.receipts_count ? 'Покупок без экономии' : 'Покупок за период нет'}
            </Text>
          )}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#F7F8F6',
    borderRadius: 18,
    padding: 16,
    gap: 10,
  },
  eyebrow: { color: DARK_GREEN, fontSize: 18, fontWeight: '900' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  chipActive: { backgroundColor: GREEN, borderColor: GREEN },
  chipText: { color: TEXT, fontSize: 13, fontWeight: '700' },
  chipTextActive: { color: '#FFFFFF' },
  loader: { marginVertical: 12 },
  amount: { color: GREEN, fontSize: 32, fontWeight: '900', lineHeight: 36 },
  period: { color: TEXT, fontSize: 15, fontWeight: '700' },
  share: { color: MUTED, fontSize: 12 },
});
