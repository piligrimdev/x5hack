import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { HistoryItem, Savings } from '@/mock-data';

interface HistoryViewProps {
  history: HistoryItem[];
  savings: Savings;
  goBack: () => void;
}

export function HistoryView({ history, savings, goBack }: HistoryViewProps) {
  const insets = useSafeAreaInsets();
  const savedAmount = savings.withoutDiscount - savings.paid;
  const savedPct = Math.round((savedAmount / savings.withoutDiscount) * 100);

  return (
    <View style={styles.root}>
      {/* Dark header */}
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goBack} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>История покупок</Text>
        {/* Placeholder for symmetry */}
        <View style={styles.backBtn} />
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>

        {/* Savings summary */}
        <View style={styles.summaryCard}>
          <View style={styles.summaryLeft}>
            <Text style={styles.summaryLabel}>СЭКОНОМЛЕНО ЗА НЕДЕЛЮ</Text>
            <Text style={styles.summaryAmount}>−{savedAmount} ₽</Text>
          </View>
          <Text style={styles.summaryPct}>{savedPct}%</Text>
        </View>

        {/* History list */}
        <View style={styles.historyList}>
          {history.map(item => (
            <HistoryCard key={item.id} item={item} />
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

function HistoryCard({ item }: { item: HistoryItem }) {
  return (
    <View style={styles.historyCard}>
      <View style={styles.storeIcon}>
        <Text style={styles.storeIconText}>М</Text>
      </View>
      <View style={styles.historyInfo}>
        <Text style={styles.historyPlace}>{item.place}</Text>
        <Text style={styles.historyMeta}>{item.dateLabel} · {item.items} товаров</Text>
      </View>
      <View style={styles.historyRight}>
        <Text style={styles.historySum}>{item.sum}</Text>
        <Text style={styles.historySaved}>−{item.saved} ₽</Text>
      </View>
      <Text style={styles.chevron}>›</Text>
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
  scroll: {
    flex: 1,
  },
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
  summaryLeft: {
    gap: 4,
  },
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
  historyList: {
    gap: 10,
  },
  historyCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  storeIcon: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: BrandColors.elementBg,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  storeIconText: {
    fontSize: 16,
    fontWeight: '700',
    color: BrandColors.textSecondary,
  },
  historyInfo: {
    flex: 1,
    gap: 3,
  },
  historyPlace: {
    fontSize: 14.5,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  historyMeta: {
    fontSize: 12.5,
    color: BrandColors.textSecondary,
  },
  historyRight: {
    alignItems: 'flex-end',
    gap: 2,
  },
  historySum: {
    fontSize: 15,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  historySaved: {
    fontSize: 11.5,
    fontWeight: '600',
    color: BrandColors.green,
  },
  chevron: {
    fontSize: 20,
    color: BrandColors.textSecondary,
    marginLeft: -4,
  },
});
