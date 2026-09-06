import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  useSavingsLeaderboard,
  type LeaderboardEntry,
  type LeaderboardMe,
} from '@/hooks/useSavingsLeaderboard';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

interface SavingsLeaderboardViewProps {
  token: string;
  goBack: () => void;
}

function rowLabel(entry: LeaderboardEntry): string {
  return entry.is_me ? 'Вы' : entry.label;
}

function MeHeader({ me, total }: { me: LeaderboardMe; total: number }) {
  const topPercent = me.top_percent;
  const showTopBadge =
    total > 1 && typeof topPercent === 'number' && topPercent <= 75;

  return (
    <View style={styles.meCard}>
      {showTopBadge ? (
        <Text style={styles.meHeadline}>
          Ты входишь в top {topPercent}% пользователей по экономности!
        </Text>
      ) : null}
      <Text style={styles.mePercent}>{me.savings_percent}%</Text>
      <Text style={styles.meCaption}>ваша доля экономии от покупок за месяц</Text>
    </View>
  );
}

function EntryRow({ entry }: { entry: LeaderboardEntry }) {
  return (
    <View style={[styles.row, entry.is_me && styles.rowMe]}>
      <Text style={styles.rowRank}>{entry.rank}</Text>
      <Text style={styles.rowLabel} numberOfLines={1}>
        {rowLabel(entry)}
      </Text>
      <Text style={styles.rowPercent}>{entry.savings_percent}%</Text>
    </View>
  );
}

export function SavingsLeaderboardView({ token, goBack }: SavingsLeaderboardViewProps) {
  const insets = useSafeAreaInsets();
  const { data, loading, error, refetch } = useSavingsLeaderboard(token);

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goBack} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Рейтинг магазина</Text>
        <View style={styles.backBtn} />
      </View>

      <ScrollView
        style={styles.body}
        contentContainerStyle={styles.bodyContent}
        showsVerticalScrollIndicator={false}>
        {loading ? (
          <ActivityIndicator color={GREEN} style={styles.loader} />
        ) : error ? (
          <View style={styles.stateCard}>
            <Text style={styles.stateTitle}>Не удалось загрузить рейтинг</Text>
            <Text style={styles.stateText}>Проверьте связь и попробуйте ещё раз.</Text>
            <TouchableOpacity style={styles.retryBtn} onPress={refetch} activeOpacity={0.8}>
              <Text style={styles.retryText}>Повторить</Text>
            </TouchableOpacity>
          </View>
        ) : data?.status === 'no_home_store' ? (
          <View style={styles.stateCard}>
            <Text style={styles.stateTitle}>Совершите покупку</Text>
            <Text style={styles.stateText}>
              Рейтинг появится, когда по вашим покупкам можно будет определить ваш магазин.
            </Text>
          </View>
        ) : (
          <>
            <Text style={styles.storeName}>{data?.store?.name ?? 'Ваш магазин'}</Text>
            <Text style={styles.storeHint}>10 ближайших соседей · процент экономии за месяц</Text>

            {data?.me ? (
              <MeHeader me={data.me} total={data.participant_count} />
            ) : (
              <View style={styles.stateCard}>
                <Text style={styles.stateTitle}>Место появится после покупки в этом месяце</Text>
                <Text style={styles.stateText}>
                  Рейтинг уже считается по вашему магазину. Своё место вы увидите, когда появится процент за текущий месяц.
                </Text>
              </View>
            )}

            {data?.solo ? (
              <Text style={styles.soloHint}>
                Вы пока один в рейтинге этого магазина. Сравнение появится, когда появятся другие покупатели.
              </Text>
            ) : null}

            <View style={styles.list}>
              {(data?.entries ?? []).map((entry, index) => (
                <EntryRow key={`${entry.rank}-${entry.label}-${index}`} entry={entry} />
              ))}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  backBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  backBtnText: { color: DARK_GREEN, fontSize: 22, fontWeight: '700' },
  headerTitle: { color: DARK_GREEN, fontSize: 17, fontWeight: '800' },
  body: { flex: 1 },
  bodyContent: { paddingHorizontal: 18, paddingTop: 18, paddingBottom: 32, gap: 12 },
  loader: { marginTop: 48 },
  storeName: { color: DARK_GREEN, fontSize: 22, fontWeight: '900' },
  storeHint: { color: MUTED, fontSize: 13, lineHeight: 18, marginTop: -4 },
  meCard: {
    backgroundColor: '#F7F8F6',
    borderRadius: 18,
    padding: 16,
    gap: 4,
  },
  meHeadline: { color: DARK_GREEN, fontSize: 18, fontWeight: '900', lineHeight: 24 },
  mePercent: { color: GREEN, fontSize: 36, fontWeight: '900', lineHeight: 40 },
  meCaption: { color: MUTED, fontSize: 12 },
  list: {
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#FFFFFF',
  },
  row: {
    minHeight: 56,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  rowMe: { backgroundColor: '#F2F8DF' },
  rowRank: { width: 28, color: MUTED, fontSize: 15, fontWeight: '800' },
  rowLabel: { flex: 1, color: TEXT, fontSize: 15, fontWeight: '700' },
  rowPercent: { color: GREEN, fontSize: 16, fontWeight: '900' },
  stateCard: {
    backgroundColor: '#F7F8F6',
    borderRadius: 16,
    padding: 16,
    gap: 8,
  },
  stateTitle: { color: DARK_GREEN, fontSize: 17, fontWeight: '800' },
  stateText: { color: MUTED, fontSize: 14, lineHeight: 20 },
  retryBtn: {
    alignSelf: 'flex-start',
    backgroundColor: GREEN,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginTop: 4,
  },
  retryText: { color: '#FFFFFF', fontSize: 14, fontWeight: '800' },
  soloHint: { color: MUTED, fontSize: 13, lineHeight: 18 },
});
