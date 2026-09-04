import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { type ChallengeItem, type PastChallengeItem, useChallenges } from '@/hooks/useChallenges';

interface ChallengesViewProps {
  token: string;
  goBack: () => void;
}

function formatDeadline(iso: string): string {
  const diffDays = Math.ceil((new Date(iso).getTime() - Date.now()) / 86400000);
  if (diffDays < 0) return 'Истекло';
  if (diffDays === 0) return 'Сегодня';
  if (diffDays === 1) return 'Завтра';
  return `Ещё ${diffDays} дн.`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

function ActiveChallengeCard({ item }: { item: ChallengeItem }) {
  const pct = Math.min(100, Math.round((item.quantity_current / item.quantity_target) * 100));
  const daysLeft = Math.ceil((new Date(item.deadline).getTime() - Date.now()) / 86400000);
  const isUrgent = daysLeft <= 2 && daysLeft >= 0;

  return (
    <View style={styles.taskCard}>
      <View style={styles.taskTopRow}>
        <View style={styles.taskTextBlock}>
          <Text style={styles.taskTitle}>{item.title}</Text>
          <Text style={styles.taskDesc}>{item.description}</Text>
        </View>
        <View style={[styles.progressPill, isUrgent && styles.progressPillUrgent]}>
          <Text style={[styles.progressPillText, isUrgent && styles.progressPillTextUrgent]}>
            {item.quantity_current}/{item.quantity_target}
          </Text>
        </View>
      </View>

      <View style={styles.taskProgressTrack}>
        <View style={[styles.taskProgressFill, { width: `${pct}%` as `${number}%` }]} />
      </View>

      <View style={styles.taskFooter}>
        <View style={styles.deadlineRow}>
          <Text style={[styles.deadlineText, isUrgent && styles.deadlineUrgent]}>
            ⏰ {formatDeadline(item.deadline)}
          </Text>
          <Text style={styles.pctText}>{pct}%</Text>
        </View>
        <View style={styles.rewardBlock}>
          <View style={styles.rewardDot} />
          <Text style={styles.rewardText}>+{item.reward_rub} ₽ при выполнении</Text>
        </View>
      </View>
    </View>
  );
}

function CompletedChallengeRow({ item, isLast }: { item: PastChallengeItem; isLast: boolean }) {
  const isDone = item.status === 'выполнено' || item.status === 'completed' || item.status === 'done';

  return (
    <View style={[styles.completedRow, !isLast && styles.completedRowBorder]}>
      <View style={[styles.completedIcon, isDone && styles.completedIconDone]}>
        <Text style={styles.completedIconText}>{isDone ? '✓' : '✗'}</Text>
      </View>
      <View style={styles.completedInfo}>
        <Text style={styles.completedTitle} numberOfLines={1}>{item.title}</Text>
        <Text style={styles.completedMeta}>
          {item.completed_at ? formatDate(item.completed_at) : formatDate(item.deadline)}
        </Text>
      </View>
      {isDone && (
        <Text style={styles.completedReward}>+{item.reward_rub} ₽</Text>
      )}
    </View>
  );
}

export function ChallengesView({ token, goBack }: ChallengesViewProps) {
  const insets = useSafeAreaInsets();
  const { current, history, loading, error } = useChallenges(token);

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goBack} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Задания</Text>
        <View style={styles.backBtn} />
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>

        {loading && <ActivityIndicator color={BrandColors.green} style={styles.loader} />}

        {!loading && error && (
          <Text style={styles.errorText}>Не удалось загрузить задания</Text>
        )}

        {!loading && !error && (
          <>
            {current.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>Активные задания</Text>
                <View style={styles.list}>
                  {current.map(item => (
                    <ActiveChallengeCard key={item.id} item={item} />
                  ))}
                </View>
              </>
            )}

            {current.length === 0 && (
              <View style={styles.emptyState}>
                <Text style={styles.emptyIcon}>🎯</Text>
                <Text style={styles.emptyText}>Нет активных заданий</Text>
              </View>
            )}

            {history.length > 0 && (
              <>
                <Text style={styles.sectionTitle}>Выполненные задания</Text>
                <View style={styles.completedCard}>
                  {history.map((item, idx) => (
                    <CompletedChallengeRow
                      key={item.id}
                      item={item}
                      isLast={idx === history.length - 1}
                    />
                  ))}
                </View>
              </>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: BrandColors.appBg,
  },
  header: {
    backgroundColor: BrandColors.dark,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 20,
    borderBottomLeftRadius: 28,
    borderBottomRightRadius: 28,
  },
  backBtn: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backBtnText: {
    color: '#fff',
    fontSize: 20,
  },
  headerTitle: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
  },
  scroll: { flex: 1 },
  scrollContent: {
    padding: 16,
    gap: 16,
  },
  loader: { marginVertical: 24 },
  errorText: {
    fontSize: 15,
    color: BrandColors.textSecondary,
    textAlign: 'center',
    marginVertical: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  list: { gap: 12 },
  taskCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 14,
    gap: 10,
  },
  taskTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
  },
  taskTextBlock: {
    flex: 1,
    gap: 4,
  },
  taskTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  taskDesc: {
    fontSize: 13,
    color: BrandColors.textSecondary,
    lineHeight: 18,
  },
  progressPill: {
    backgroundColor: BrandColors.elementBg,
    borderRadius: 100,
    paddingVertical: 3,
    paddingHorizontal: 10,
    marginTop: 2,
    flexShrink: 0,
  },
  progressPillUrgent: {
    backgroundColor: '#FFF0EF',
  },
  progressPillText: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    fontWeight: '600',
  },
  progressPillTextUrgent: {
    color: BrandColors.red,
  },
  taskProgressTrack: {
    height: 7,
    backgroundColor: BrandColors.elementBg,
    borderRadius: 100,
    overflow: 'hidden',
  },
  taskProgressFill: {
    height: 7,
    borderRadius: 100,
    backgroundColor: BrandColors.red,
  },
  taskFooter: { gap: 8 },
  deadlineRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  deadlineText: {
    fontSize: 12.5,
    color: BrandColors.textSecondary,
  },
  deadlineUrgent: {
    color: BrandColors.red,
    fontWeight: '600',
  },
  pctText: {
    fontSize: 12.5,
    fontWeight: '600',
    color: BrandColors.textSecondary,
  },
  rewardBlock: {
    backgroundColor: BrandColors.rewardOrangeBg,
    borderRadius: 10,
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  rewardDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: BrandColors.gold,
    flexShrink: 0,
  },
  rewardText: {
    fontSize: 12.5,
    color: BrandColors.textPrimary,
    flex: 1,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 48,
    gap: 12,
  },
  emptyIcon: { fontSize: 40 },
  emptyText: {
    fontSize: 15,
    color: BrandColors.textSecondary,
  },
  completedCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    overflow: 'hidden',
  },
  completedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 14,
  },
  completedRowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.04)',
  },
  completedIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: BrandColors.elementBg,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  completedIconDone: {
    backgroundColor: BrandColors.greenLight,
  },
  completedIconText: {
    fontSize: 13,
    fontWeight: '700',
    color: BrandColors.green,
  },
  completedInfo: {
    flex: 1,
    gap: 2,
  },
  completedTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  completedMeta: {
    fontSize: 12,
    color: BrandColors.textSecondary,
  },
  completedReward: {
    fontSize: 14,
    fontWeight: '700',
    color: BrandColors.green,
  },
});
