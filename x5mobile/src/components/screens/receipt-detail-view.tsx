import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { useReceiptDetail } from '@/hooks/useReceiptDetail';

interface ReceiptDetailViewProps {
  token: string;
  receiptId: string;
  goBack: () => void;
}

function formatMoney(v: number): string {
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) + ' ₽';
}

export function ReceiptDetailView({ token, receiptId, goBack }: ReceiptDetailViewProps) {
  const insets = useSafeAreaInsets();
  const { detail, loading, error } = useReceiptDetail(token, receiptId);

  const storeName = detail
    ? [detail.store.format_name, detail.store.geo_cluster].filter(Boolean).join(', ') || 'Магазин'
    : 'Покупка';

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goBack} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>{storeName}</Text>
        <View style={styles.backBtn} />
      </View>

      {loading && (
        <View style={styles.centerContainer}>
          <ActivityIndicator color={BrandColors.green} size="large" />
        </View>
      )}

      {!loading && error && (
        <View style={styles.centerContainer}>
          <Text style={styles.errorText}>Не удалось загрузить покупку</Text>
        </View>
      )}

      {!loading && !error && detail && (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}>

          <View style={styles.summaryCard}>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Без скидок</Text>
              <Text style={styles.summaryValue}>{formatMoney(detail.total_base)}</Text>
            </View>
            {detail.discount_saved_rub > 0 && (
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Скидка</Text>
                <Text style={[styles.summaryValue, styles.savedValue]}>−{formatMoney(detail.discount_saved_rub)}</Text>
              </View>
            )}
            {detail.cashback_applied_rub > 0 && (
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>
                  Бонусы{detail.cashback_applied_points > 0 ? ` (${detail.cashback_applied_points})` : ''}
                </Text>
                <Text style={[styles.summaryValue, styles.savedValue]}>−{formatMoney(detail.cashback_applied_rub)}</Text>
              </View>
            )}
            <View style={[styles.summaryRow, styles.summaryRowTotal]}>
              <Text style={styles.summaryLabelTotal}>Итого оплачено</Text>
              <Text style={styles.summaryValueTotal}>{formatMoney(detail.total_paid)}</Text>
            </View>
          </View>

          <Text style={styles.sectionTitle}>Товары ({detail.items.length})</Text>

          <View style={styles.productList}>
            {detail.items.map((item, idx) => {
              const totalBase = item.base_price_at_purchase * item.quantity;
              const totalPaid = item.paid_price * item.quantity;
              const totalDiscount = item.discounted_amount * item.quantity;

              return (
                <View
                  key={item.product_id}
                  style={[styles.productRow, idx < detail.items.length - 1 && styles.productRowBorder]}>
                  <View style={styles.productInfo}>
                    <Text style={styles.productName}>{item.product_name}</Text>
                    {item.quantity > 1 && (
                      <Text style={styles.productQty}>
                        {item.quantity} шт. × {formatMoney(item.base_price_at_purchase)}
                      </Text>
                    )}
                  </View>
                  <View style={styles.productPrices}>
                    {totalDiscount > 0 && (
                      <Text style={styles.productBase}>{formatMoney(totalBase)}</Text>
                    )}
                    {totalDiscount > 0 && (
                      <Text style={styles.productDiscount}>−{formatMoney(totalDiscount)}</Text>
                    )}
                    <Text style={styles.productPaid}>{formatMoney(totalPaid)}</Text>
                  </View>
                </View>
              );
            })}
          </View>
        </ScrollView>
      )}
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
    flex: 1,
    textAlign: 'center',
    marginHorizontal: 8,
  },
  centerContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  errorText: {
    fontSize: 15,
    color: BrandColors.textSecondary,
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
    gap: 10,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  summaryRowTotal: {
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: BrandColors.cardBorder,
  },
  summaryLabel: {
    fontSize: 14,
    color: BrandColors.textSecondary,
  },
  summaryLabelTotal: {
    fontSize: 15,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  summaryValue: {
    fontSize: 14,
    color: BrandColors.textPrimary,
    fontWeight: '500',
  },
  summaryValueTotal: {
    fontSize: 17,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  savedValue: {
    color: BrandColors.green,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  productList: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    overflow: 'hidden',
  },
  productRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    padding: 14,
  },
  productRowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.04)',
  },
  productInfo: {
    flex: 1,
    gap: 3,
  },
  productName: {
    fontSize: 14,
    fontWeight: '500',
    color: BrandColors.textPrimary,
    lineHeight: 19,
  },
  productQty: {
    fontSize: 12,
    color: BrandColors.textSecondary,
  },
  productPrices: {
    alignItems: 'flex-end',
    gap: 2,
    flexShrink: 0,
  },
  productBase: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    textDecorationLine: 'line-through',
  },
  productDiscount: {
    fontSize: 12,
    color: BrandColors.green,
    fontWeight: '600',
  },
  productPaid: {
    fontSize: 14,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
});
