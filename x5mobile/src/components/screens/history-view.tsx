import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { useReceipts } from '@/hooks/useReceipts';

import { ReceiptListItem } from './ReceiptListItem';

interface HistoryViewProps {
  token: string;
  totalSaved: number;
  totalPaid: number;
  goBack: () => void;
  onReceiptPress: (id: string) => void;
}

export function HistoryView({ token, totalSaved, totalPaid, goBack, onReceiptPress }: HistoryViewProps) {
  const insets = useSafeAreaInsets();
  const { receipts, loading, error } = useReceipts(token);

  const withoutDiscount = totalPaid + totalSaved;
  const savedPct = withoutDiscount > 0
    ? Math.round((totalSaved / withoutDiscount) * 100)
    : 0;

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goBack} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>История покупок</Text>
        <View style={styles.backBtn} />
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>

        <View style={styles.summaryCard}>
          <View style={styles.summaryLeft}>
            <Text style={styles.summaryLabel}>СЭКОНОМЛЕНО ВСЕГО</Text>
            <Text style={styles.summaryAmount}>
              −{Math.round(totalSaved).toLocaleString('ru-RU')} ₽
            </Text>
          </View>
          {savedPct > 0 && <Text style={styles.summaryPct}>{savedPct}%</Text>}
        </View>

        <View style={styles.historyList}>
          {loading && (
            <ActivityIndicator color={BrandColors.green} style={styles.loader} />
          )}
          {!loading && error && (
            <Text style={styles.emptyText}>Не удалось загрузить покупки</Text>
          )}
          {!loading && !error && receipts.length === 0 && (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>🛒</Text>
              <Text style={styles.emptyText}>Покупок пока нет</Text>
            </View>
          )}
          {receipts.map((r) => (
            <ReceiptListItem key={r.id} item={r} onPress={() => onReceiptPress(r.id)} />
          ))}
        </View>
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
  summaryCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  summaryLeft: { gap: 4 },
  summaryLabel: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  summaryAmount: {
    fontSize: 19,
    fontWeight: '700',
    color: BrandColors.green,
  },
  summaryPct: {
    fontSize: 20,
    fontWeight: '700',
    color: BrandColors.green,
  },
  historyList: { gap: 10 },
  loader: { marginVertical: 24 },
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
});
