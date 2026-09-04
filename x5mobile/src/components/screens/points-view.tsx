import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { usePointsBalance, usePointsTransactions } from '@/hooks/usePoints';

interface PointsViewProps {
  token: string;
  goBack: () => void;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
}

export function PointsView({ token, goBack }: PointsViewProps) {
  const insets = useSafeAreaInsets();
  const { balance, loading: balanceLoading, refresh: refreshBalance } = usePointsBalance(token);
  const { page, loading: txLoading, refresh: refreshTx } = usePointsTransactions(token, 20);

  const refreshing = balanceLoading || txLoading;

  async function onRefresh() {
    await Promise.all([refreshBalance(), refreshTx()]);
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goBack} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Мои баллы</Text>
        <View style={styles.backBtn} />
      </View>

      <ScrollView
        style={styles.body}
        contentContainerStyle={styles.bodyContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        <View style={styles.balanceCard}>
          <Text style={styles.balanceLabel}>Баланс кешбека</Text>
          <Text style={styles.balanceValue}>{balance?.balance ?? 0}</Text>
          <Text style={styles.balanceSub}>баллов</Text>
          {balance ? (
            <View style={styles.rateRow}>
              <Text style={styles.rateText}>
                ≈ {balance.balance_rub_equivalent} ₽ · курс {balance.rate_points_per_rub} баллов = 1 ₽
              </Text>
            </View>
          ) : null}
        </View>

        <Text style={styles.sectionTitle}>История</Text>
        {txLoading && !page ? (
          <ActivityIndicator style={{ marginTop: 24 }} color={BrandColors.green} />
        ) : null}
        {page?.items.length === 0 ? (
          <Text style={styles.emptyText}>Пока нет операций. Выполните задание — получите баллы.</Text>
        ) : null}
        {page?.items.map((tx) => (
          <View key={tx.id} style={styles.txRow}>
            <View style={styles.txInfo}>
              <Text style={styles.txType}>{tx.type === 'earn' ? 'Начисление' : 'Списание'}</Text>
              <Text style={styles.txDate}>{formatDate(tx.created_at)}</Text>
            </View>
            <Text style={[styles.txAmount, tx.type === 'earn' ? styles.txEarn : styles.txSpend]}>
              {tx.type === 'earn' ? '+' : ''}
              {tx.amount}
            </Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 16,
    backgroundColor: '#fff',
  },
  backBtn: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backBtnText: {
    fontSize: 24,
    color: BrandColors.textPrimary,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  body: {
    flex: 1,
  },
  bodyContent: {
    padding: 16,
    paddingBottom: 32,
  },
  balanceCard: {
    backgroundColor: BrandColors.green,
    padding: 24,
    borderRadius: 16,
    marginBottom: 24,
  },
  balanceLabel: {
    color: '#fff',
    opacity: 0.85,
    fontSize: 14,
  },
  balanceValue: {
    color: '#fff',
    fontSize: 44,
    fontWeight: '700',
    marginTop: 4,
  },
  balanceSub: {
    color: '#fff',
    opacity: 0.85,
    fontSize: 16,
    marginTop: 2,
  },
  rateRow: {
    marginTop: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.25)',
    paddingTop: 12,
  },
  rateText: {
    color: '#fff',
    opacity: 0.9,
    fontSize: 13,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: BrandColors.textPrimary,
    marginBottom: 12,
  },
  emptyText: {
    color: BrandColors.textSecondary,
    fontSize: 14,
    textAlign: 'center',
    marginTop: 16,
  },
  txRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.06)',
  },
  txInfo: {
    flex: 1,
  },
  txType: {
    fontSize: 14,
    color: BrandColors.textPrimary,
    fontWeight: '500',
  },
  txDate: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    marginTop: 2,
  },
  txAmount: {
    fontSize: 16,
    fontWeight: '600',
  },
  txEarn: {
    color: BrandColors.green,
  },
  txSpend: {
    color: BrandColors.textPrimary,
  },
});
