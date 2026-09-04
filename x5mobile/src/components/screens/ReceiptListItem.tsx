import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { BrandColors } from '@/constants/theme';
import type { ReceiptListItem as ReceiptListItemType } from '@/hooks/useReceipts';

function _formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const days = Math.floor(diff / 86400000);
  const time = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  if (days === 0) return `Сегодня, ${time}`;
  if (days === 1) return `Вчера, ${time}`;
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) + `, ${time}`;
}

function _formatMoney(value: number): string {
  return value.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽';
}

interface Props {
  item: ReceiptListItemType;
  onPress?: () => void;
}

export function ReceiptListItem({ item, onPress }: Props) {
  const label = [item.store_format_name, item.store_geo_cluster].filter(Boolean).join(', ') || 'Магазин';

  return (
    <TouchableOpacity style={styles.card} activeOpacity={0.7} onPress={onPress}>
      <View style={styles.icon}>
        <Text style={styles.iconText}>{item.store_format_name ? item.store_format_name[0].toUpperCase() : 'М'}</Text>
      </View>
      <View style={styles.info}>
        <Text style={styles.place} numberOfLines={1}>{label}</Text>
        <Text style={styles.meta}>{_formatDate(item.purchase_date)} · {item.items_count} товаров</Text>
      </View>
      <View style={styles.right}>
        <Text style={styles.sum}>{_formatMoney(item.total_paid)}</Text>
        {item.total_saved > 0 && (
          <Text style={styles.saved}>−{_formatMoney(item.total_saved)}</Text>
        )}
      </View>
      <Text style={styles.chevron}>›</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  icon: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: BrandColors.elementBg,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  iconText: {
    fontSize: 16,
    fontWeight: '700',
    color: BrandColors.textSecondary,
  },
  info: {
    flex: 1,
    gap: 3,
  },
  place: {
    fontSize: 14.5,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  meta: {
    fontSize: 12.5,
    color: BrandColors.textSecondary,
  },
  right: {
    alignItems: 'flex-end',
    gap: 2,
  },
  sum: {
    fontSize: 15,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  saved: {
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
