import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useEconomy } from '@/hooks/useEconomy';
import { useReceipts } from '@/hooks/useReceipts';

const ORANGE = '#FF6D00';
const GREEN_BANNER = '#1B5E35';
const GREEN_BTN = '#2DB35E';
const GREEN_ACTIVE = '#25A244';

const RU_MONTHS = ['январе', 'феврале', 'марте', 'апреле', 'мае', 'июне', 'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре'];

function fmt(n: number) {
  return Math.round(n).toLocaleString('ru-RU');
}

interface HomeViewProps {
  token: string;
  onHistory: () => void;
}

export function HomeView({ token, onHistory }: HomeViewProps) {
  const insets = useSafeAreaInsets();
  const { economy, loading: eLoading } = useEconomy(token);
  const { receipts } = useReceipts(token);

  const totalSaved = economy?.total_saved ?? 0;
  const totalPaid = economy?.total_paid ?? 0;
  const receiptsCount = economy?.receipts_count ?? 0;

  // Points = total_saved rounded (hackathon proxy for loyalty points)
  const points = Math.round(totalSaved);
  // Daily benefit: average per receipt
  const todayBenefit = receiptsCount > 0 ? Math.round(totalSaved / receiptsCount) : 0;

  // Percentile: how much of paid was saved (higher = more economical)
  const savingsRate = (totalPaid + totalSaved) > 0
    ? totalSaved / (totalPaid + totalSaved)
    : 0;
  const percentile = Math.min(99, Math.round(savingsRate * 100 * 8));

  // Progress to next cashback level (every 1000 saved = new level)
  const levelThreshold = 1000;
  const levelProgress = (totalSaved % levelThreshold) / levelThreshold;
  const toNextLevel = Math.round(levelThreshold - (totalSaved % levelThreshold));

  const monthName = RU_MONTHS[new Date().getMonth()];

  // Last receipt for "Заказывали" preview
  const lastReceipt = receipts[0];

  return (
    <View style={styles.root}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <TouchableOpacity activeOpacity={0.7}>
          <View style={styles.addressRow}>
            <Text style={styles.addressText}>Большая Пушкарская, 32</Text>
            <Text style={styles.chevron}> ›</Text>
          </View>
          <Text style={styles.deliveryText}>Доставка от 30 минут</Text>
        </TouchableOpacity>
        <View style={styles.headerActions}>
          <TouchableOpacity style={styles.headerBtn} activeOpacity={0.7}>
            <Text style={styles.headerBtnIcon}>💬</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.headerBtn} activeOpacity={0.7}>
            <Text style={styles.headerBtnIcon}>🛒</Text>
            <View style={styles.cartBadge}>
              <Text style={styles.cartBadgeText}>1</Text>
            </View>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>

        {/* X5 Клуб Banner */}
        <View style={styles.banner}>
          <View style={styles.bannerLeft}>
            <View style={styles.x5LogoRow}>
              <View style={styles.x5Shield}>
                <Text style={styles.x5ShieldText}>X5</Text>
              </View>
              <Text style={styles.x5ClubText}>Клуб</Text>
            </View>
            {eLoading ? (
              <ActivityIndicator color="#fff" style={{ marginVertical: 10 }} />
            ) : (
              <>
                <Text style={styles.bannerPoints}>{fmt(points)}</Text>
                <Text style={styles.bannerPointsLabel}>баллов</Text>
                <Text style={styles.bannerSavings}>
                  Ваша выгода сегодня —{'\n'}
                  <Text style={styles.bannerSavingsAmount}>{fmt(todayBenefit)} ₽</Text>
                </Text>
              </>
            )}
            <TouchableOpacity style={styles.openCardBtn} activeOpacity={0.8}>
              <Text style={styles.openCardBtnText}>Открыть карту</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.bannerRight}>
            <View style={styles.speechBubble}>
              <Text style={styles.speechBubbleText}>Нашёл{'\n'}цены ниже</Text>
            </View>
            <Image
              source={require('../../../assets/images/mascot.png')}
              style={styles.mascotImage}
              resizeMode="contain"
            />
          </View>
        </View>

        {/* Скажите, что хочется */}
        <View style={styles.askCard}>
          <View style={styles.askIcon}>
            <Text style={styles.askIconEmoji}>🍊</Text>
          </View>
          <View style={styles.askText}>
            <Text style={styles.askTitle}>Скажите, что хочется</Text>
            <Text style={styles.askSubtitle}>Аппи найдёт выгоднее{'\n'}и соберёт корзину</Text>
          </View>
          <View style={styles.askActions}>
            <TouchableOpacity style={styles.micBtn} activeOpacity={0.8}>
              <Text style={styles.micIcon}>🎙</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.findBtn} activeOpacity={0.8}>
              <Text style={styles.findBtnText}>Найти</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Quick actions — 4 иконки */}
        <View style={styles.quickRow}>
          <TouchableOpacity style={styles.quickItem} activeOpacity={0.7} onPress={onHistory}>
            <View style={styles.quickIconBox}>
              <Text style={styles.quickIconChar}>⏱</Text>
            </View>
            <Text style={styles.quickLabel}>Заказывали</Text>
            {lastReceipt && (
              <Text style={styles.quickSub}>{fmt(lastReceipt.total_paid)} ₽</Text>
            )}
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickItem} activeOpacity={0.7}>
            <View style={styles.quickIconBox}>
              <Text style={styles.quickIconChar}>%</Text>
            </View>
            <Text style={styles.quickLabel}>Скидки</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickItem} activeOpacity={0.7}>
            <View style={styles.quickIconBox}>
              <Text style={styles.quickIconChar}>♡</Text>
            </View>
            <Text style={styles.quickLabel}>Избранное</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickItem} activeOpacity={0.7}>
            <View style={styles.quickIconBox}>
              <Text style={styles.quickIconChar}>⊞</Text>
            </View>
            <Text style={styles.quickLabel}>Каталог</Text>
          </TouchableOpacity>
        </View>

        {/* Ваша экономия */}
        <View style={styles.savingsCard}>
          <Text style={styles.savingsTitle}>Ваша экономия</Text>
          {eLoading ? (
            <ActivityIndicator color={GREEN_ACTIVE} style={{ marginVertical: 12 }} />
          ) : (
            <>
              <View style={styles.savingsAmountRow}>
                <Text style={styles.savingsAmount}>{fmt(totalSaved)} ₽</Text>
                <Text style={styles.savingsMonth}>  за {monthName}</Text>
              </View>

              {/* Progress bar */}
              <View style={styles.progressBarRow}>
                <Text style={styles.progressLabel}>обычно</Text>
                <View style={styles.progressTrack}>
                  <View style={[styles.progressFill, { width: `${Math.min(100, percentile)}%` }]} />
                  <View style={[styles.percentileBadge, { left: `${Math.min(90, Math.max(10, percentile))}%` }]}>
                    <Text style={styles.percentileBadgeText}>{percentile}%</Text>
                  </View>
                </View>
                <Text style={styles.progressLabel}>очень выгодно</Text>
              </View>

              <Text style={styles.savingsPct}>
                Вы экономнее{' '}
                <Text style={styles.savingsPctHighlight}>{percentile}%</Text>
                {' '}покупателей
              </Text>

              <Text style={styles.nextLevelHint}>
                Ещё {fmt(toNextLevel)} ₽ — и новый уровень кешбэка
              </Text>

              {/* Next level bar */}
              <View style={styles.nextLevelTrack}>
                <View style={[styles.nextLevelFill, { width: `${Math.round(levelProgress * 100)}%` }]} />
              </View>

              <TouchableOpacity activeOpacity={0.7}>
                <Text style={styles.howToSave}>Как сэкономить ещё ›</Text>
              </TouchableOpacity>
            </>
          )}
        </View>

        {/* Для вас сегодня */}
        <Text style={styles.forYouTitle}>Для вас сегодня</Text>
        <View style={styles.promoRow}>
          {/* Позовите друга */}
          <View style={[styles.promoCard, { backgroundColor: '#F9F0E8' }]}>
            <Text style={styles.promoCardTitle}>Позовите друга</Text>
            <Text style={styles.promoCardSub}>+500 баллов{'\n'}каждому</Text>
            <Text style={styles.promoEmoji}>🤝</Text>
            <TouchableOpacity style={styles.promoOrangeBtn} activeOpacity={0.8}>
              <Text style={styles.promoOrangeBtnText}>Поделиться</Text>
            </TouchableOpacity>
          </View>

          {/* Соберите 3 в ряд */}
          <View style={[styles.promoCard, { backgroundColor: '#F0F7F1' }]}>
            <Text style={styles.promoCardTitle}>Соберите 3 в ряд</Text>
            <Text style={styles.promoCardSub}>Откройте скидку{'\n'}на любимый кофе</Text>
            <View style={styles.puzzleGrid}>
              {['🍅','🥑','🧀','🧀','🍅','🥑','🥑','🧀','🍅'].map((e, i) => (
                <Text key={i} style={styles.puzzleEmoji}>{e}</Text>
              ))}
            </View>
            <TouchableOpacity style={styles.promoGreenBtn} activeOpacity={0.8}>
              <Text style={styles.promoGreenBtnText}>Играть</Text>
            </TouchableOpacity>
          </View>
        </View>

      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F5F5F2' },

  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 12,
    backgroundColor: '#F5F5F2',
  },
  addressRow: { flexDirection: 'row', alignItems: 'center' },
  addressText: { fontSize: 17, fontWeight: '800', color: '#17171A' },
  chevron: { fontSize: 18, color: '#17171A', fontWeight: '700' },
  deliveryText: { fontSize: 13, color: '#8A8A8E', marginTop: 2 },
  headerActions: { flexDirection: 'row', gap: 8 },
  headerBtn: {
    width: 42, height: 42, borderRadius: 12,
    backgroundColor: '#EBEBEB',
    alignItems: 'center', justifyContent: 'center',
  },
  headerBtnIcon: { fontSize: 18 },
  cartBadge: {
    position: 'absolute', top: -4, right: -4,
    backgroundColor: ORANGE, borderRadius: 10,
    width: 18, height: 18, alignItems: 'center', justifyContent: 'center',
  },
  cartBadgeText: { color: '#fff', fontSize: 10, fontWeight: '700' },

  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 16, paddingBottom: 24, gap: 12 },

  // Banner
  banner: {
    backgroundColor: GREEN_BANNER, borderRadius: 20,
    padding: 20, paddingRight: 0,
    flexDirection: 'row', overflow: 'hidden', minHeight: 190,
  },
  bannerLeft: { flex: 1, gap: 2 },
  x5LogoRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 },
  x5Shield: {
    backgroundColor: 'rgba(255,255,255,0.15)', borderRadius: 6,
    paddingHorizontal: 7, paddingVertical: 3,
  },
  x5ShieldText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  x5ClubText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  bannerPoints: { color: '#fff', fontSize: 36, fontWeight: '800', lineHeight: 40 },
  bannerPointsLabel: { color: 'rgba(255,255,255,0.75)', fontSize: 15, fontWeight: '500', marginTop: -2, marginBottom: 4 },
  bannerSavings: { color: 'rgba(255,255,255,0.8)', fontSize: 13, fontWeight: '500', lineHeight: 18, marginBottom: 12 },
  bannerSavingsAmount: { color: '#fff', fontSize: 18, fontWeight: '800' },
  openCardBtn: {
    backgroundColor: '#fff', borderRadius: 100,
    paddingVertical: 10, paddingHorizontal: 18,
    alignSelf: 'flex-start',
  },
  openCardBtnText: { color: '#17171A', fontSize: 14, fontWeight: '700' },
  bannerRight: {
    width: 140, alignItems: 'center',
    justifyContent: 'flex-end', position: 'relative',
  },
  speechBubble: {
    position: 'absolute', top: 0, right: 16,
    backgroundColor: '#fff', borderRadius: 14,
    paddingHorizontal: 12, paddingVertical: 8, zIndex: 1,
  },
  speechBubbleText: { fontSize: 13, fontWeight: '600', color: '#17171A', textAlign: 'center' },
  mascotImage: { width: 140, height: 170 },

  // Ask card
  askCard: {
    backgroundColor: '#fff', borderRadius: 16, padding: 14,
    flexDirection: 'row', alignItems: 'center', gap: 10,
    borderWidth: 1, borderColor: 'rgba(0,0,0,0.06)',
  },
  askIcon: {
    width: 48, height: 48, borderRadius: 24,
    backgroundColor: '#FFF3E0', alignItems: 'center', justifyContent: 'center',
  },
  askIconEmoji: { fontSize: 26 },
  askText: { flex: 1 },
  askTitle: { fontSize: 15, fontWeight: '700', color: '#17171A' },
  askSubtitle: { fontSize: 12, color: '#8A8A8E', lineHeight: 16, marginTop: 2 },
  askActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  micBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: '#F5F5F2', alignItems: 'center', justifyContent: 'center',
  },
  micIcon: { fontSize: 20 },
  findBtn: {
    backgroundColor: GREEN_BTN, borderRadius: 100,
    paddingVertical: 10, paddingHorizontal: 16,
  },
  findBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },

  // Quick row
  quickRow: {
    backgroundColor: '#fff', borderRadius: 16,
    flexDirection: 'row', paddingVertical: 14, paddingHorizontal: 8,
    borderWidth: 1, borderColor: 'rgba(0,0,0,0.06)',
  },
  quickItem: { flex: 1, alignItems: 'center', gap: 5 },
  quickIconBox: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: '#F5F5F2', alignItems: 'center', justifyContent: 'center',
  },
  quickIconChar: { fontSize: 20, color: '#17171A', fontWeight: '600' },
  quickLabel: { fontSize: 11.5, fontWeight: '500', color: '#17171A', textAlign: 'center' },
  quickSub: { fontSize: 10, color: GREEN_ACTIVE, fontWeight: '600' },

  // Savings
  savingsCard: {
    backgroundColor: '#fff', borderRadius: 16, padding: 16,
    borderWidth: 1, borderColor: 'rgba(0,0,0,0.06)', gap: 8,
  },
  savingsTitle: { fontSize: 20, fontWeight: '800', color: '#17171A' },
  savingsAmountRow: { flexDirection: 'row', alignItems: 'flex-end' },
  savingsAmount: { fontSize: 28, fontWeight: '800', color: GREEN_ACTIVE },
  savingsMonth: { fontSize: 15, color: '#8A8A8E', marginBottom: 4 },

  progressBarRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4,
  },
  progressLabel: { fontSize: 10, color: '#8A8A8E', flexShrink: 0 },
  progressTrack: {
    flex: 1, height: 8, backgroundColor: '#E8E8E8', borderRadius: 4, overflow: 'visible',
    position: 'relative',
  },
  progressFill: {
    height: '100%', backgroundColor: GREEN_ACTIVE, borderRadius: 4,
  },
  percentileBadge: {
    position: 'absolute', top: -10,
    backgroundColor: ORANGE, borderRadius: 100,
    paddingHorizontal: 6, paddingVertical: 2,
    transform: [{ translateX: -16 }],
  },
  percentileBadgeText: { color: '#fff', fontSize: 10, fontWeight: '700' },

  savingsPct: { fontSize: 14, color: '#17171A', marginTop: 8 },
  savingsPctHighlight: { color: ORANGE, fontWeight: '700' },

  nextLevelHint: { fontSize: 13, color: '#8A8A8E' },
  nextLevelTrack: {
    height: 6, backgroundColor: '#E8E8E8', borderRadius: 3,
  },
  nextLevelFill: {
    height: '100%', backgroundColor: GREEN_ACTIVE, borderRadius: 3,
  },
  howToSave: { fontSize: 14, color: GREEN_ACTIVE, fontWeight: '600' },

  // For you
  forYouTitle: { fontSize: 20, fontWeight: '800', color: '#17171A' },
  promoRow: { flexDirection: 'row', gap: 10 },
  promoCard: {
    flex: 1, borderRadius: 16, padding: 14, gap: 4, minHeight: 180,
  },
  promoCardTitle: { fontSize: 14, fontWeight: '800', color: '#17171A' },
  promoCardSub: { fontSize: 12, color: '#8A8A8E', lineHeight: 16 },
  promoEmoji: { fontSize: 48, textAlign: 'center', marginVertical: 6 },
  promoOrangeBtn: {
    backgroundColor: ORANGE, borderRadius: 100,
    paddingVertical: 8, paddingHorizontal: 14, alignSelf: 'flex-start', marginTop: 4,
  },
  promoOrangeBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  puzzleGrid: {
    flexDirection: 'row', flexWrap: 'wrap', width: '100%', marginVertical: 6, gap: 2,
  },
  puzzleEmoji: { fontSize: 22, width: '30%', textAlign: 'center' },
  promoGreenBtn: {
    backgroundColor: GREEN_ACTIVE, borderRadius: 100,
    paddingVertical: 8, paddingHorizontal: 14, alignSelf: 'flex-start', marginTop: 2,
  },
  promoGreenBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
});
