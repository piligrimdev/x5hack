import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { isBasketChallenge, useChallenges } from '@/hooks/useChallenges';
import { useEconomy } from '@/hooks/useEconomy';
import { useMonthlyEconomy } from '@/hooks/useMonthlyEconomy';

const GREEN = '#138F3E';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E9EBE9';
const RU_MONTHS = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
];

function formatNumber(value: number): string {
  return Math.round(value).toLocaleString('ru-RU');
}

function formatRub(value: number): string {
  return value.toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function challengeIcon(title: string): string {
  const lower = title.toLowerCase();
  if (lower.includes('коф')) return '☕';
  if (lower.includes('молоч') || lower.includes('молок')) return '🥛';
  if (lower.includes('овощ') || lower.includes('салат')) return '🥗';
  if (lower.includes('хлеб')) return '🥖';
  return '🛍️';
}

interface PersonalChallengesProps {
  token: string;
  onDetails: () => void;
  limit?: number;
  showHeading?: boolean;
}

export function PersonalChallenges({
  token,
  onDetails,
  limit = 2,
  showHeading = true,
}: PersonalChallengesProps) {
  const { current, loading, error } = useChallenges(token);
  const visible = current.slice(0, limit);

  return (
    <View style={styles.section}>
      {showHeading && <Text style={styles.sectionTitle}>Персональные задания</Text>}
      <View style={styles.challengeList}>
        {loading ? (
          <ActivityIndicator color={GREEN} style={styles.loading} />
        ) : error ? (
          <Text style={styles.emptyText}>Не удалось загрузить задания</Text>
        ) : visible.length === 0 ? (
          <Text style={styles.emptyText}>Новые задания скоро появятся</Text>
        ) : (
          visible.map((challenge, index) => {
            const taskItems = challenge.items ?? [];
            const firstItem = taskItems[0];
            const currentValue = isBasketChallenge(challenge)
              ? 0
              : firstItem?.quantity_current ?? challenge.quantity_current;
            const targetValue = firstItem?.quantity_target ?? challenge.quantity_target;
            const progress = taskItems.length > 1
              ? `${taskItems.filter(item => item.quantity_current >= item.quantity_target).length} из ${taskItems.length} пунктов`
              : `${currentValue} из ${targetValue}`;

            return (
              <View
                key={challenge.id}
                style={[styles.challengeRow, index > 0 && styles.challengeBorder]}>
                <View style={styles.challengeIcon}>
                  <Text style={styles.challengeEmoji}>{challengeIcon(challenge.title)}</Text>
                </View>
                <View style={styles.challengeText}>
                  <Text style={styles.challengeTitle} numberOfLines={1}>{challenge.title}</Text>
                  <Text style={styles.challengeDescription} numberOfLines={1}>
                    {currentValue > 0 ? progress : challenge.description}
                  </Text>
                </View>
                <View style={styles.challengeReward}>
                  <Text style={styles.rewardText}>+{formatNumber(challenge.reward_rub)} баллов</Text>
                  <TouchableOpacity style={styles.detailsButton} onPress={onDetails} activeOpacity={0.75}>
                    <Text style={styles.detailsText}>Подробнее</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })
        )}
      </View>
    </View>
  );
}

interface EconomyCardProps {
  token: string;
  onChallenges: () => void;
}

export function EconomyCard({ token, onChallenges }: EconomyCardProps) {
  const { economy, loading: economyLoading } = useEconomy(token);
  const { monthlyEconomy, loading: monthlyLoading } = useMonthlyEconomy(token);
  const loading = economyLoading || monthlyLoading;
  const months = monthlyEconomy?.months ?? [];
  const currentSaved = monthlyEconomy?.currentMonthSaved ?? 0;
  const totalSaved = economy?.total_saved ?? 0;
  const streak = monthlyEconomy?.consecutiveGrowthMonths ?? 0;
  const maxSaved = Math.max(...months.map(month => month.saved), 1);

  return (
    <View style={styles.economyCard}>
      <Text style={styles.economyTitle}>Ваша экономия{streak > 0 ? ' растёт' : ''}</Text>
      {loading ? (
        <ActivityIndicator color={GREEN} style={styles.loading} />
      ) : (
        <>
          <Text style={styles.economyAmount}>{formatRub(currentSaved)} ₽</Text>
          <Text style={styles.economyMonth}>за {RU_MONTHS[new Date().getMonth()]}</Text>
          {months.length > 0 && (
            <View style={styles.chart}>
              <View style={styles.chartBars}>
                {months.map((month, index) => (
                  <View
                    key={month.key}
                    style={[
                      styles.chartBar,
                      {
                        height: Math.max(6, (month.saved / maxSaved) * 56),
                        backgroundColor: index === months.length - 1 ? GREEN : '#E5E7E5',
                      },
                    ]}
                  />
                ))}
              </View>
              <View style={styles.chartLabels}>
                {months.map(month => (
                  <Text key={month.key} style={styles.chartLabel}>{month.label}</Text>
                ))}
              </View>
            </View>
          )}
          <View style={styles.economyFooter}>
            <Text style={styles.economyTotal}>Всего сэкономлено {formatRub(totalSaved)} ₽</Text>
            <TouchableOpacity onPress={onChallenges} activeOpacity={0.7}>
              <Text style={styles.economyLink}>Увеличить выгоду ›</Text>
            </TouchableOpacity>
          </View>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: 10 },
  sectionTitle: { color: '#164E2B', fontSize: 19, fontWeight: '800' },
  challengeList: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 16,
    overflow: 'hidden',
  },
  loading: { marginVertical: 24 },
  emptyText: { color: MUTED, fontSize: 13, textAlign: 'center', paddingVertical: 22 },
  challengeRow: {
    minHeight: 78,
    paddingHorizontal: 12,
    paddingVertical: 11,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  challengeBorder: { borderTopWidth: 1, borderTopColor: BORDER },
  challengeIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#F2F8DF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  challengeEmoji: { fontSize: 25 },
  challengeText: { flex: 1, minWidth: 0, gap: 3 },
  challengeTitle: { color: TEXT, fontSize: 14, fontWeight: '800' },
  challengeDescription: { color: MUTED, fontSize: 11, lineHeight: 15 },
  challengeReward: { alignItems: 'flex-end', gap: 7 },
  rewardText: { color: GREEN, fontSize: 12, fontWeight: '800' },
  detailsButton: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#BED6C5',
  },
  detailsText: { color: '#357747', fontSize: 11, fontWeight: '600' },

  economyCard: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 17,
    padding: 16,
    gap: 4,
  },
  economyTitle: { color: TEXT, fontSize: 20, fontWeight: '800' },
  economyAmount: { color: TEXT, fontSize: 36, lineHeight: 42, fontWeight: '800', marginTop: 2 },
  economyMonth: { color: MUTED, fontSize: 13 },
  chart: { marginTop: 8 },
  chartBars: { height: 60, flexDirection: 'row', alignItems: 'flex-end', gap: 6 },
  chartBar: { flex: 1, borderRadius: 5 },
  chartLabels: { flexDirection: 'row', gap: 6, marginTop: 4 },
  chartLabel: { flex: 1, textAlign: 'center', color: '#A0A3A0', fontSize: 10 },
  economyFooter: {
    marginTop: 10,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: BORDER,
    gap: 7,
  },
  economyTotal: { color: MUTED, fontSize: 12 },
  economyLink: { color: GREEN, fontSize: 13, fontWeight: '700' },
});
