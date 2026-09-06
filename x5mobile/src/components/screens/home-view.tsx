import { SymbolView } from 'expo-symbols';
import type { ImageSourcePropType } from 'react-native';
import {
  ActivityIndicator,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { useEconomy } from '@/hooks/useEconomy';
import { usePointsBalance } from '@/hooks/usePoints';

const SKY = '#1599C8';
const CLUB_GREEN = '#42AF35';
const ORANGE = '#FF6A18';
const PINK = '#F95B8B';
const TEXT = '#292929';

const QR_PATTERN = [
  '11101011101',
  '10111010001',
  '11101110111',
  '00011000100',
  '10101110111',
  '01110010100',
  '11001101101',
  '00110110010',
  '11101011101',
  '10011100101',
  '11100111111',
];

interface HomeViewProps {
  token: string;
  onPoints?: () => void;
  onOpenAppi: () => void;
  onHistory: () => void;
}

interface ReplaceableIconProps {
  emoji: string;
  imageSource?: ImageSourcePropType;
  imageStyle?: object;
  color?: string;
  fontSize?: number;
}

/**
 * Temporary emoji slot. Pass imageSource for a PNG; this wrapper can also be
 * replaced by an SVG component without changing the surrounding card layout.
 */
function ReplaceableIcon({
  emoji,
  imageSource,
  imageStyle,
  color,
  fontSize,
}: ReplaceableIconProps) {
  if (imageSource) {
    return <Image source={imageSource} style={[styles.replaceableImage, imageStyle]} resizeMode="contain" />;
  }
  return <Text style={[styles.replaceableEmoji, { color, fontSize }]}>{emoji}</Text>;
}

function ClubQr() {
  return (
    <View style={styles.qrCard}>
      <View style={styles.qrGrid}>
        {QR_PATTERN.join('').split('').map((cell, index) => (
          <View key={index} style={[styles.qrCell, cell === '1' && styles.qrCellFilled]} />
        ))}
      </View>
    </View>
  );
}

function QuickAction({
  emoji,
  label,
  color,
  onPress,
}: {
  emoji: string;
  label: string;
  color: string;
  onPress?: () => void;
}) {
  return (
    <TouchableOpacity style={styles.quickAction} activeOpacity={0.72} onPress={onPress}>
      <View style={[styles.quickIcon, { backgroundColor: color }]}>
        <ReplaceableIcon emoji={emoji} />
      </View>
      <Text style={styles.quickLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

export function HomeView({ token, onPoints, onOpenAppi, onHistory }: HomeViewProps) {
  const insets = useSafeAreaInsets();
  const { balance, loading: pointsLoading } = usePointsBalance(token);
  const { economy } = useEconomy(token);

  const totalSaved = economy?.total_saved ?? 0;
  const totalPaid = economy?.total_paid ?? 0;
  const withoutDiscount = totalPaid + totalSaved;
  const savedPct = withoutDiscount > 0 ? Math.round((totalSaved / withoutDiscount) * 100) : 0;

  function formatRub(value: number): string {
    return value.toLocaleString('ru-RU', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>
        <View style={[styles.sky, { paddingTop: insets.top + 7 }]}>
          <View style={styles.topBar}>
            <View style={styles.deliveryToggle}>
              <View style={styles.walkCircle}>
                <SymbolView
                  name={{ ios: 'figure.walk', android: 'directions_walk', web: 'directions_walk' }}
                  tintColor="#151515"
                  size={21}
                  weight="bold"
                />
              </View>
              <View style={styles.carGhost}>
                <SymbolView
                  name={{ ios: 'car.fill', android: 'directions_car', web: 'directions_car' }}
                  tintColor="#FFFFFF"
                  size={17}
                />
              </View>
            </View>
            <TouchableOpacity style={styles.addressButton} activeOpacity={0.75}>
              <Text style={styles.addressText}>Укажите адрес</Text>
              <Text style={styles.addressArrow}>›</Text>
            </TouchableOpacity>
            <View style={styles.topActions}>
              <TouchableOpacity style={styles.topActionButton} activeOpacity={0.75}>
                <SymbolView
                  name={{ ios: 'bell.fill', android: 'notifications', web: 'notifications' }}
                  tintColor="#111111"
                  size={18}
                  weight="semibold"
                />
              </TouchableOpacity>
              <TouchableOpacity style={styles.topActionButton} activeOpacity={0.75}>
                <SymbolView
                  name={{ ios: 'questionmark.circle.fill', android: 'help', web: 'help' }}
                  tintColor="#111111"
                  size={18}
                  weight="semibold"
                />
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.loyaltyRow}>
            <TouchableOpacity style={styles.clubCard} onPress={onPoints} activeOpacity={0.9}>
              <View style={styles.clubTop}>
                <View style={styles.clubLogo}>
                  <ReplaceableIcon emoji="✕" color="#FFFFFF" fontSize={21} />
                  <Text style={styles.clubLogoText}>X5 Клуб ›</Text>
                </View>
                <ClubQr />
              </View>

              <View style={styles.clubBalance}>
                {pointsLoading ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <>
                    <Text style={styles.clubBalanceValue}>
                      {(balance?.balance ?? 0).toLocaleString('ru-RU')} ✕
                    </Text>
                    <Text style={styles.clubBalanceRub}>
                      {Math.round(balance?.balance_rub_equivalent ?? 0).toLocaleString('ru-RU')} ₽
                    </Text>
                  </>
                )}
              </View>

              <View style={styles.clubFooter}>
                <View style={styles.cashbackCircle}><Text style={styles.cashbackArrow}>↶</Text></View>
                <View style={styles.cashbackCopy}>
                  <Text style={styles.cashbackLabel}>Кешбэк</Text>
                  <Text style={styles.cashbackValue}>0.5%</Text>
                </View>
                <TouchableOpacity style={styles.chooseButton} onPress={onPoints} activeOpacity={0.8}>
                  <Text style={styles.chooseButtonText}>Выбрать 3</Text>
                  <Text style={styles.chooseButtonIcon}>♣</Text>
                </TouchableOpacity>
              </View>
            </TouchableOpacity>

            <View style={styles.orangeCard}>
              <View style={styles.orangeLogo}>
                <ReplaceableIcon emoji="◒" color="#FFFFFF" fontSize={20} />
                <Text style={styles.orangeLogoText}>апельсин</Text>
              </View>
              <Text style={styles.orangeDescription}>
                1088 ✕ и кешбэк{'\n'}7% на все покупки{'\n'}по карте
              </Text>
              <TouchableOpacity style={styles.receiveButton} activeOpacity={0.8}>
                <Text style={styles.receiveButtonText}>Получить</Text>
              </TouchableOpacity>
            </View>
          </View>

        </View>

        <View style={styles.contentSheet}>
          <View style={styles.actionsRow}>
            <QuickAction emoji="🍅" label={'История\nпокупок'} color="#FFF1D8" onPress={onHistory} />
            <QuickAction emoji="⭐" label={'Оценка\nтоваров'} color="#FFF3C9" />
            <QuickAction emoji="%" label={'Моя\nвыгода'} color="#FFE9E4" onPress={onPoints} />
          </View>

          <TouchableOpacity style={styles.economyCard} onPress={onOpenAppi} activeOpacity={0.8}>
            <Text style={styles.economyLabel}>ЭКОНОМИЯ</Text>
            <View style={styles.economyRow}>
              <Text style={styles.economyAmount}>−{formatRub(totalSaved)} ₽</Text>
              {savedPct > 0 && <Text style={styles.economyPct}>{savedPct}%</Text>}
            </View>
          </TouchableOpacity>

          <TouchableOpacity style={styles.saleBanner} activeOpacity={0.9}>
            <View style={styles.saleCopy}>
              <View style={styles.saleBadge}><Text style={styles.saleBadgeText}>До −40%</Text></View>
              <Text style={styles.saleTitle}>Скидки{'\n'}недели</Text>
              <View style={styles.orderButton}><Text style={styles.orderButtonText}>Заказать</Text></View>
            </View>
            <View style={styles.saleCircle}>
              <Text style={styles.tomato}>🍅</Text>
              <Text style={styles.milkBottle}>🧴</Text>
              <Text style={styles.cheese}>🧀</Text>
              <Text style={styles.fire}>🔥</Text>
            </View>
          </TouchableOpacity>

          <Text style={styles.recommendTitle}>Вам понравится</Text>
          <TouchableOpacity style={styles.addressNotice} activeOpacity={0.78}>
            <Text style={styles.warning}>⚠️</Text>
            <Text style={styles.addressNoticeText}>
              Выберите адрес, чтобы видеть{'\n'}актуальные цены и наличие
            </Text>
            <Text style={styles.noticeArrow}>›</Text>
          </TouchableOpacity>

          <View style={styles.promoCode}>
            <View style={styles.promoIcon}><Text style={styles.promoIconText}>%</Text></View>
            <Text style={styles.promoText}>Промокод −500₽ на заказ от 1 000₽ · </Text>
            <Text style={styles.promoStrong}>ЛУЧИ500</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  scroll: { flex: 1 },
  scrollContent: { backgroundColor: '#FFFFFF' },
  sky: {
    backgroundColor: SKY,
    paddingBottom: 18,
    overflow: 'hidden',
  },

  topBar: {
    height: 54,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
  },
  deliveryToggle: {
    width: 88,
    height: 43,
    borderRadius: 22,
    backgroundColor: 'rgba(255,255,255,0.28)',
    flexDirection: 'row',
    alignItems: 'center',
    padding: 3,
  },
  walkCircle: {
    width: 37,
    height: 37,
    borderRadius: 19,
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 2,
  },
  carGhost: { flex: 1, alignItems: 'center', opacity: 0.42 },
  addressButton: {
    marginLeft: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    flex: 1,
  },
  addressText: { color: '#FFFFFF', fontSize: 14, fontWeight: '600' },
  addressArrow: { color: '#FFFFFF', fontSize: 22, lineHeight: 22 },
  topActions: {
    backgroundColor: '#FFFFFF',
    height: 43,
    borderRadius: 22,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 9,
    gap: 12,
  },
  topActionButton: { width: 18, height: 30, alignItems: 'center', justifyContent: 'center' },

  loyaltyRow: {
    height: 179,
    flexDirection: 'row',
    gap: 9,
    paddingLeft: 17,
    paddingRight: 9,
    marginTop: 8,
  },
  clubCard: {
    flex: 2.05,
    backgroundColor: CLUB_GREEN,
    borderRadius: 19,
    padding: 13,
    overflow: 'hidden',
  },
  clubTop: { flexDirection: 'row', justifyContent: 'space-between' },
  clubLogo: { flexDirection: 'row', alignItems: 'center', gap: 3, height: 27 },
  clubLogoText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  replaceableEmoji: { fontSize: 21 },
  replaceableImage: { width: 42, height: 42 },
  qrCard: { width: 92, height: 92, borderRadius: 7, backgroundColor: '#FFFFFF', padding: 7 },
  qrGrid: { flex: 1, flexDirection: 'row', flexWrap: 'wrap' },
  qrCell: { width: '9.09%', height: '9.09%', backgroundColor: '#FFFFFF' },
  qrCellFilled: { backgroundColor: '#111111' },
  clubBalance: { position: 'absolute', left: 13, top: 57, gap: 1 },
  clubBalanceValue: { color: '#FFFFFF', fontSize: 28, lineHeight: 31, fontWeight: '900' },
  clubBalanceRub: { color: '#FFFFFF', fontSize: 11, fontWeight: '700' },
  clubFooter: {
    position: 'absolute',
    left: 13,
    right: 12,
    bottom: 9,
    height: 43,
    flexDirection: 'row',
    alignItems: 'center',
  },
  cashbackCircle: {
    width: 34, height: 34, borderRadius: 17, backgroundColor: '#9BDD42',
    alignItems: 'center', justifyContent: 'center',
  },
  cashbackArrow: { color: '#388625', fontSize: 23, lineHeight: 24, fontWeight: '900' },
  cashbackCopy: { marginLeft: 7 },
  cashbackLabel: { color: '#FFFFFF', fontSize: 10, fontWeight: '700' },
  cashbackValue: { color: '#FFFFFF', fontSize: 16, lineHeight: 17, fontWeight: '900' },
  chooseButton: {
    marginLeft: 'auto',
    height: 36,
    borderRadius: 18,
    backgroundColor: '#E92936',
    paddingHorizontal: 15,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  chooseButtonText: { color: '#FFFFFF', fontSize: 12, fontWeight: '900' },
  chooseButtonIcon: { color: '#FFFFFF', fontSize: 15 },

  orangeCard: {
    flex: 1,
    borderRadius: 19,
    backgroundColor: ORANGE,
    padding: 14,
    justifyContent: 'space-between',
  },
  orangeLogo: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  orangeLogoText: { color: '#FFFFFF', fontSize: 16, fontWeight: '900' },
  orangeDescription: { color: '#FFFFFF', fontSize: 11, lineHeight: 16, fontWeight: '600' },
  receiveButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    paddingHorizontal: 17,
    paddingVertical: 9,
  },
  receiveButtonText: { color: TEXT, fontSize: 12, fontWeight: '900' },

  contentSheet: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 31,
    borderTopRightRadius: 31,
    marginTop: -6,
    paddingTop: 17,
    paddingHorizontal: 17,
    paddingBottom: 32,
    gap: 20,
  },
  actionsRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  quickAction: { flex: 1, alignItems: 'center', gap: 5 },
  quickIcon: {
    width: 52,
    height: 52,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  quickLabel: { color: TEXT, fontSize: 10.5, lineHeight: 14, textAlign: 'center', fontWeight: '600' },
  economyCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 16,
    gap: 8,
  },
  economyLabel: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  economyRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  economyAmount: {
    fontSize: 22,
    fontWeight: '800',
    color: BrandColors.green,
  },
  economyPct: {
    fontSize: 22,
    fontWeight: '800',
    color: BrandColors.green,
  },

  saleBanner: {
    height: 239,
    borderRadius: 19,
    backgroundColor: PINK,
    overflow: 'hidden',
    padding: 21,
  },
  saleCopy: { zIndex: 3, alignItems: 'flex-start' },
  saleBadge: {
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    paddingHorizontal: 13,
    paddingVertical: 7,
  },
  saleBadgeText: { color: TEXT, fontSize: 13, fontWeight: '900' },
  saleTitle: { color: '#FFFFFF', fontSize: 31, lineHeight: 34, fontWeight: '900', marginTop: 17 },
  orderButton: {
    backgroundColor: '#FFFFFF',
    borderRadius: 21,
    paddingHorizontal: 20,
    paddingVertical: 11,
    marginTop: 23,
  },
  orderButtonText: { color: TEXT, fontSize: 14, fontWeight: '900' },
  saleCircle: {
    position: 'absolute',
    width: 210,
    height: 210,
    borderRadius: 105,
    backgroundColor: '#FFA719',
    right: -24,
    top: 14,
  },
  tomato: { position: 'absolute', fontSize: 65, left: 5, top: 64, transform: [{ rotate: '-15deg' }] },
  milkBottle: { position: 'absolute', fontSize: 92, left: 65, top: 23, transform: [{ rotate: '8deg' }] },
  cheese: { position: 'absolute', fontSize: 72, right: 0, top: 86, transform: [{ rotate: '-10deg' }] },
  fire: { position: 'absolute', fontSize: 45, left: 72, bottom: 1 },

  recommendTitle: { color: TEXT, fontSize: 19, fontWeight: '900', marginTop: 3 },
  addressNotice: {
    minHeight: 66,
    borderRadius: 15,
    backgroundColor: '#FFF7E8',
    paddingHorizontal: 13,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  warning: { fontSize: 20 },
  addressNoticeText: { flex: 1, color: '#555955', fontSize: 12, lineHeight: 17 },
  noticeArrow: { color: '#6C716C', fontSize: 28 },
  promoCode: {
    minHeight: 38,
    borderRadius: 19,
    backgroundColor: '#FFD77A',
    marginTop: -31,
    marginHorizontal: 28,
    paddingHorizontal: 11,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#D59C27',
    shadowOpacity: 0.22,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 4,
  },
  promoIcon: {
    width: 22, height: 22, borderRadius: 11, backgroundColor: '#F5AD32',
    alignItems: 'center', justifyContent: 'center',
  },
  promoIconText: { color: '#FFFFFF', fontSize: 12, fontWeight: '900' },
  promoText: { color: '#6B542B', fontSize: 9.5, marginLeft: 7 },
  promoStrong: { color: '#4B3A1D', fontSize: 9.5, fontWeight: '900' },
});
