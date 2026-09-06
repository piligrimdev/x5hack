import { ActivityIndicator, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PersonalChallenges } from '@/components/screens/personal-sections';
import { usePointsBalance } from '@/hooks/usePoints';

const GREEN = '#138F3E';
const DARK_GREEN = '#075C2C';
const ORANGE = '#F56A00';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E9EBE9';

const PERSONAL_OFFERS = [
  {
    id: 'cheese',
    emoji: '🧀',
    title: 'Сыр\nк завтраку',
    benefit: '−15% по карте',
    background: '#FFF8E3',
  },
  {
    id: 'coffee',
    emoji: '☕',
    title: 'Ваш любимый\nкофе',
    benefit: '+10% баллами',
    background: '#F6F4EB',
  },
];

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
  onChallenges: () => void;
  onPoints?: () => void;
  onOpenAppi: () => void;
  onHistory: () => void;
}

function ClubQr() {
  return (
    <View style={styles.qrCard}>
      <View style={styles.qrGrid}>
        {QR_PATTERN.join('').split('').map((cell, index) => (
          <View
            key={index}
            style={[styles.qrCell, cell === '1' && styles.qrCellFilled]}
          />
        ))}
      </View>
    </View>
  );
}

function WhiteMicrophoneIcon() {
  return (
    <View style={styles.whiteMicrophone}>
      <View style={styles.whiteMicrophoneCapsule} />
      <View style={styles.whiteMicrophoneStem} />
      <View style={styles.whiteMicrophoneBase} />
    </View>
  );
}

export function HomeView({
  token,
  onChallenges,
  onPoints,
  onOpenAppi,
  onHistory,
}: HomeViewProps) {
  const insets = useSafeAreaInsets();
  const { balance, loading: pointsLoading } = usePointsBalance(token);

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <View>
          <View style={styles.addressRow}>
            <Text style={styles.address}>Большая Пушкарская, 32</Text>
            <Text style={styles.addressChevron}>⌄</Text>
          </View>
          <Text style={styles.delivery}>Доставка от 30 минут</Text>
        </View>
        <TouchableOpacity style={styles.cartButton} activeOpacity={0.75}>
          <Text style={styles.cartIcon}>⌑</Text>
          <View style={styles.cartBadge}><Text style={styles.cartBadgeText}>3</Text></View>
        </TouchableOpacity>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}>
        <TouchableOpacity style={styles.clubCard} activeOpacity={0.9} onPress={onPoints}>
          <View style={styles.clubInfo}>
            <View style={styles.clubBrand}>
              <Text style={styles.x5Mark}>X5</Text>
              <Text style={styles.clubText}>Клуб</Text>
            </View>
            {pointsLoading ? (
              <ActivityIndicator color="#FFFFFF" style={styles.pointsLoader} />
            ) : (
              <View style={styles.balanceRow}>
                <Text style={styles.balance}>{(balance?.balance ?? 0).toLocaleString('ru-RU')}</Text>
                <Text style={styles.balanceUnit}>балла</Text>
              </View>
            )}
            <View style={styles.cardHint}>
              <Text style={styles.cardHintIcon}>▣</Text>
              <Text style={styles.cardHintText}>Карта для покупок</Text>
            </View>
          </View>
          <ClubQr />
        </TouchableOpacity>

        <TouchableOpacity style={styles.historyButton} onPress={onHistory} activeOpacity={0.8}>
          <View style={styles.historyIcon}>
            <Text style={styles.historyEmoji}>🕐</Text>
          </View>
          <View style={styles.historyCopy}>
            <Text style={styles.historyTitle}>История покупок</Text>
            <Text style={styles.historySubtitle}>Чеки и сэкономленные рубли</Text>
          </View>
          <Text style={styles.historyChevron}>›</Text>
        </TouchableOpacity>

        <View style={styles.appiCard}>
          <Image
            source={require('../../../assets/images/mascot.png')}
            style={styles.appiMascot}
            resizeMode="contain"
          />
          <View style={styles.appiContent}>
            <Text style={styles.appiQuestion}>Что собрать для вас?</Text>
            <TouchableOpacity style={styles.appiInput} onPress={onOpenAppi} activeOpacity={0.8}>
              <Text style={styles.appiPlaceholder}>Напишите или скажите Аппи</Text>
              <View style={styles.micCircle}><WhiteMicrophoneIcon /></View>
              <View style={styles.sendCircle}><Text style={styles.sendArrow}>→</Text></View>
            </TouchableOpacity>
          </View>
          <View style={styles.quickActions}>
            <TouchableOpacity style={styles.quickButton} onPress={onOpenAppi} activeOpacity={0.75}>
              <Text style={styles.quickIcon}>🍴</Text>
              <Text style={styles.quickText}>Ужин до 700 ₽</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.quickButton} onPress={onOpenAppi} activeOpacity={0.75}>
              <Text style={styles.repeatIcon}>↻</Text>
              <Text style={styles.quickText}>Повторить покупки</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Персональные акции</Text>
            <Text style={styles.sectionChevron}>›</Text>
          </View>
          <View style={styles.offerRow}>
            {PERSONAL_OFFERS.map(offer => (
              <View key={offer.id} style={[styles.offerCard, { backgroundColor: offer.background }]}>
                <Text style={styles.offerEmoji}>{offer.emoji}</Text>
                <View style={styles.offerInfo}>
                  <Text style={styles.offerTitle}>{offer.title}</Text>
                  <Text style={styles.offerBenefit}>{offer.benefit}</Text>
                  <TouchableOpacity style={styles.offerButton} activeOpacity={0.75}>
                    <Text style={styles.offerButtonText}>Условия</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        </View>

        <PersonalChallenges token={token} onDetails={onChallenges} />

        <View style={styles.partnerBanner}>
          <View style={styles.partnerCopy}>
            <Text style={styles.partnerTitle}>Выгода{'\n'}от партнёров</Text>
            <TouchableOpacity style={styles.partnerButton} activeOpacity={0.8}>
              <Text style={styles.partnerButtonText}>Подробнее</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.partnerProducts}>
            <Text style={styles.partnerCoffee}>☕</Text>
            <Text style={styles.partnerPizza}>🍕</Text>
            <Text style={styles.partnerMilk}>🥛</Text>
          </View>
          <Text style={styles.adLabel}>Реклама</Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  header: {
    paddingHorizontal: 22,
    paddingBottom: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
  },
  addressRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  address: { color: TEXT, fontSize: 18, fontWeight: '800' },
  addressChevron: { color: TEXT, fontSize: 18, fontWeight: '700', marginTop: -5 },
  delivery: { color: MUTED, fontSize: 13, marginTop: 3 },
  cartButton: {
    width: 47,
    height: 47,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: BORDER,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cartIcon: { color: TEXT, fontSize: 29, lineHeight: 31, transform: [{ rotate: '180deg' }] },
  cartBadge: {
    position: 'absolute',
    top: -5,
    right: -5,
    width: 19,
    height: 19,
    borderRadius: 10,
    backgroundColor: '#E52D35',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cartBadgeText: { color: '#FFFFFF', fontSize: 10, fontWeight: '800' },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 16, paddingBottom: 26, gap: 18 },

  clubCard: {
    minHeight: 168,
    borderRadius: 20,
    backgroundColor: DARK_GREEN,
    padding: 22,
    flexDirection: 'row',
    alignItems: 'center',
    overflow: 'hidden',
  },
  clubInfo: { flex: 1, alignSelf: 'stretch', justifyContent: 'space-between' },
  clubBrand: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  x5Mark: { color: '#FFFFFF', fontSize: 24, fontWeight: '900', fontStyle: 'italic' },
  clubText: { color: '#FFFFFF', fontSize: 20, fontWeight: '600' },
  pointsLoader: { alignSelf: 'flex-start' },
  balanceRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  balance: { color: '#FFFFFF', fontSize: 46, lineHeight: 50, fontWeight: '800' },
  balanceUnit: { color: '#FFFFFF', fontSize: 14, marginBottom: 7 },
  cardHint: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(0,0,0,0.22)',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  cardHintIcon: { color: '#FFFFFF', fontSize: 16 },
  cardHintText: { color: '#FFFFFF', fontSize: 12, fontWeight: '600' },
  qrCard: { width: 126, height: 126, borderRadius: 12, backgroundColor: '#FFFFFF', padding: 10 },
  qrGrid: { flex: 1, flexDirection: 'row', flexWrap: 'wrap' },
  qrCell: { width: '9.09%', height: '9.09%', backgroundColor: '#FFFFFF' },
  qrCellFilled: { backgroundColor: '#111111' },

  historyButton: {
    minHeight: 72,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  historyIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#F2F8DF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  historyEmoji: { fontSize: 22 },
  historyCopy: { flex: 1, gap: 2 },
  historyTitle: { color: TEXT, fontSize: 15, fontWeight: '800' },
  historySubtitle: { color: MUTED, fontSize: 12 },
  historyChevron: { color: '#6F7570', fontSize: 28, lineHeight: 28 },

  appiCard: {
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 18,
    padding: 13,
    paddingTop: 17,
    minHeight: 168,
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#FFFFFF',
  },
  appiMascot: { width: 92, height: 94, marginLeft: -8, marginTop: -7 },
  appiContent: { flex: 1, gap: 10 },
  appiQuestion: { color: TEXT, fontSize: 16, fontWeight: '800' },
  appiInput: {
    height: 43,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: BORDER,
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: 13,
    gap: 7,
  },
  appiPlaceholder: { color: '#A1A4A1', fontSize: 11, flex: 1 },
  micCircle: {
    width: 34, height: 34, borderRadius: 17, backgroundColor: ORANGE,
    alignItems: 'center', justifyContent: 'center',
  },
  whiteMicrophone: { width: 15, height: 20, alignItems: 'center' },
  whiteMicrophoneCapsule: {
    width: 8, height: 12, borderRadius: 4, borderWidth: 1.5, borderColor: '#FFFFFF',
  },
  whiteMicrophoneStem: { width: 1.5, height: 4, backgroundColor: '#FFFFFF' },
  whiteMicrophoneBase: { width: 8, height: 1.5, borderRadius: 1, backgroundColor: '#FFFFFF' },
  sendCircle: {
    width: 34, height: 34, borderRadius: 17, backgroundColor: GREEN,
    alignItems: 'center', justifyContent: 'center', marginRight: 4,
  },
  sendArrow: { color: '#FFFFFF', fontSize: 23, lineHeight: 25 },
  quickActions: {
    position: 'absolute',
    left: 13,
    right: 13,
    bottom: 13,
    flexDirection: 'row',
    gap: 9,
  },
  quickButton: {
    flex: 1,
    height: 38,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: BORDER,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    backgroundColor: '#FFFFFF',
  },
  quickIcon: { fontSize: 14 },
  repeatIcon: { color: GREEN, fontSize: 18 },
  quickText: { color: TEXT, fontSize: 11, fontWeight: '600' },

  section: { gap: 10 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 6 },
  sectionTitle: { color: '#164E2B', fontSize: 19, fontWeight: '800' },
  sectionChevron: { color: '#6F7570', fontSize: 29, lineHeight: 29 },
  offerRow: { flexDirection: 'row', gap: 8 },
  offerCard: {
    flex: 1,
    height: 145,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 10,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  offerEmoji: { fontSize: 60, alignSelf: 'flex-end', marginLeft: -15, marginBottom: 15 },
  offerInfo: { flex: 1, gap: 3, marginLeft: -1 },
  offerTitle: { color: TEXT, fontSize: 13, lineHeight: 16, fontWeight: '800' },
  offerBenefit: { color: GREEN, fontSize: 11, fontWeight: '700' },
  offerButton: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(255,255,255,0.76)',
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
    marginTop: 'auto',
  },
  offerButtonText: { color: MUTED, fontSize: 10, fontWeight: '600' },

  partnerBanner: {
    minHeight: 130,
    borderRadius: 17,
    backgroundColor: ORANGE,
    overflow: 'hidden',
    flexDirection: 'row',
    padding: 18,
  },
  partnerCopy: { zIndex: 2 },
  partnerTitle: { color: '#FFFFFF', fontSize: 22, lineHeight: 26, fontWeight: '800' },
  partnerButton: {
    marginTop: 10,
    alignSelf: 'flex-start',
    backgroundColor: '#FFFFFF',
    borderRadius: 9,
    paddingHorizontal: 15,
    paddingVertical: 8,
  },
  partnerButtonText: { color: '#386449', fontSize: 11, fontWeight: '800' },
  partnerProducts: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    width: '58%',
    backgroundColor: '#7FBE32',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  partnerCoffee: { fontSize: 48, transform: [{ rotate: '-8deg' }] },
  partnerPizza: { fontSize: 58, marginLeft: -10, marginTop: -15 },
  partnerMilk: { fontSize: 44, marginLeft: -12, marginTop: 30 },
  adLabel: { position: 'absolute', right: 8, top: 5, color: 'rgba(255,255,255,0.8)', fontSize: 8 },
});
