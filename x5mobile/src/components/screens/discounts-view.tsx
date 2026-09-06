import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { UserDiscountOut } from '@/api/client';
import { useDiscounts } from '@/hooks/useDiscounts';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

interface DiscountsViewProps {
  token: string;
  goBack: () => void;
}

function formatUntil(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

function DiscountCard({ item }: { item: UserDiscountOut }) {
  const until = formatUntil(item.valid_to);
  return (
    <View style={styles.card}>
      <View style={styles.cardTop}>
        <Text style={styles.cardTitle}>{item.title}</Text>
        {item.is_personal ? (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>Для вас</Text>
          </View>
        ) : (
          <View style={[styles.badge, styles.badgePromo]}>
            <Text style={[styles.badgeText, styles.badgePromoText]}>Акция</Text>
          </View>
        )}
      </View>
      <Text style={styles.cardDesc}>{item.description}</Text>
      {until ? <Text style={styles.cardUntil}>Действует до {until}</Text> : null}
    </View>
  );
}

export function DiscountsView({ token, goBack }: DiscountsViewProps) {
  const insets = useSafeAreaInsets();
  const { items, loading, error } = useDiscounts(token);

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <TouchableOpacity onPress={goBack} style={styles.back} activeOpacity={0.7}>
        <Text style={styles.backText}>← Назад</Text>
      </TouchableOpacity>
      <Text style={styles.title}>Мои скидки</Text>
      <Text style={styles.subtitle}>
        Что сейчас действует на ваши покупки — персональные и общие акции
      </Text>

      {loading ? <ActivityIndicator color={GREEN} style={styles.spinner} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
        {!loading && items.length === 0 && !error ? (
          <Text style={styles.empty}>
            Пока нет активных скидок. Введите реферальный код при входе или дождитесь акций недели.
          </Text>
        ) : null}
        {items.map((item) => (
          <DiscountCard key={item.id} item={item} />
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#F6F8F6',
    paddingHorizontal: 20,
  },
  back: {
    alignSelf: 'flex-start',
    paddingVertical: 8,
  },
  backText: {
    color: GREEN,
    fontSize: 16,
    fontWeight: '600',
  },
  title: {
    color: DARK_GREEN,
    fontSize: 28,
    fontWeight: '800',
    marginTop: 8,
  },
  subtitle: {
    color: MUTED,
    fontSize: 15,
    lineHeight: 21,
    marginTop: 8,
    marginBottom: 16,
  },
  spinner: {
    marginVertical: 24,
  },
  error: {
    color: '#C0392B',
    marginBottom: 12,
  },
  empty: {
    color: MUTED,
    fontSize: 15,
    lineHeight: 22,
  },
  list: {
    paddingBottom: 40,
    gap: 12,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 16,
    gap: 8,
  },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
  },
  cardTitle: {
    color: TEXT,
    fontSize: 17,
    fontWeight: '800',
    flex: 1,
  },
  badge: {
    backgroundColor: '#E8F6EC',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  badgeText: {
    color: GREEN,
    fontSize: 12,
    fontWeight: '700',
  },
  badgePromo: {
    backgroundColor: '#FFF3E6',
  },
  badgePromoText: {
    color: '#C45C12',
  },
  cardDesc: {
    color: TEXT,
    fontSize: 14,
    lineHeight: 20,
  },
  cardUntil: {
    color: MUTED,
    fontSize: 13,
    fontWeight: '600',
  },
});
