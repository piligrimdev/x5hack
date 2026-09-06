import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { FortuneWheel, type SpinRequest } from '@/components/screens/fortune-wheel';
import type { CouponTxOut, CouponTxType } from '@/api/client';
import {
  formatWinTime,
  prizeTypeLabel,
  useFortuneWheel,
  type SpinResult,
} from '@/hooks/useFortuneWheel';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const ORANGE = '#F56A00';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

interface FortuneWheelViewProps {
  token: string;
  goBack: () => void;
}

const COUPON_TX_LABEL: Record<CouponTxType, string> = {
  weekly_grant: 'Еженедельные купоны',
  task_complete: 'За задание',
  spin: 'Крутка колеса',
  referral: 'За приглашение друга',
  purchase: 'За покупки',
};

function CouponTxRow({ item }: { item: CouponTxOut }) {
  const earn = item.amount > 0;
  return (
    <View style={styles.couponTxRow}>
      <View style={styles.historyCopy}>
        <Text style={styles.historyTitle}>{COUPON_TX_LABEL[item.type]}</Text>
        <Text style={styles.historyMeta}>{formatWinTime(item.created_at)}</Text>
      </View>
      <Text style={[styles.couponTxAmount, earn ? styles.couponTxEarn : styles.couponTxSpend]}>
        {earn ? `+${item.amount}` : item.amount}
      </Text>
    </View>
  );
}

export function FortuneWheelView({ token, goBack }: FortuneWheelViewProps) {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const { state, prizes, history, couponTx, loading, error, spin } = useFortuneWheel(token);
  const [spinRequest, setSpinRequest] = useState<SpinRequest | null>(null);
  const [animating, setAnimating] = useState(false);
  const [result, setResult] = useState<SpinResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const wheelSize = Math.min(width - 48, 320);
  const busy = animating;
  const canSpin = Boolean(state?.can_spin) && !busy && prizes.length >= 2;

  const onSpinComplete = useCallback(() => {
    setAnimating(false);
  }, []);

  async function handleSpin() {
    if (!canSpin) return;
    setActionError(null);
    setResult(null);
    setAnimating(true);
    try {
      const next = await spin();
      setResult(next.result);
      setSpinRequest({ targetIndex: next.targetIndex, nonce: Date.now() });
    } catch (e: unknown) {
      setAnimating(false);
      setActionError(e instanceof Error ? e.message : 'Не удалось крутить колесо');
    }
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goBack} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Колесо Аппи</Text>
        <View style={styles.backBtn} />
      </View>

      <ScrollView
        style={styles.body}
        contentContainerStyle={styles.bodyContent}
        showsVerticalScrollIndicator={false}>
        <Text style={styles.lead}>
          Крутите колесо за купон — приз выбирает сервер. На дольках подарки и кешбэк из вашего каталога.
        </Text>

        <View style={styles.couponCard}>
          <Text style={styles.couponValue}>{state?.coupons ?? '—'}</Text>
          <Text style={styles.couponLabel}>купонов</Text>
          {state ? (
            <Text style={styles.couponHint}>
              {state.can_spin
                ? '1 купон = 1 крутка'
                : 'Купоны за каждую 1000 ₽ покупок и за рефералов'}
            </Text>
          ) : null}
        </View>

        {loading ? (
          <ActivityIndicator color={ORANGE} style={styles.loader} />
        ) : prizes.length >= 2 ? (
          <View style={styles.wheelWrap}>
            <FortuneWheel
              prizes={prizes}
              size={wheelSize}
              spinRequest={spinRequest}
              onSpinComplete={onSpinComplete}
            />
          </View>
        ) : (
          <Text style={styles.empty}>Секторы колеса пока недоступны</Text>
        )}

        <TouchableOpacity
          style={[styles.spinButton, !canSpin && styles.spinButtonDisabled]}
          onPress={handleSpin}
          activeOpacity={0.85}
          disabled={!canSpin}>
          {busy
            ? <ActivityIndicator color="#FFFFFF" />
            : <Text style={styles.spinButtonText}>{state?.can_spin ? 'Крутить' : 'Нет купонов'}</Text>}
        </TouchableOpacity>

        {actionError || error ? (
          <Text style={styles.error}>{actionError ?? error}</Text>
        ) : null}

        {result && !animating ? (
          <View style={styles.resultCard}>
            <Text style={styles.resultEyebrow}>Выигрыш</Text>
            <Text style={styles.resultTitle}>{result.prize_label}</Text>
            <Text style={styles.resultText}>
              {result.prize_type === 'gift'
                ? 'Подарок уже в наградах — применится в следующей покупке.'
                : result.points_awarded != null
                  ? `Начислено ${result.points_awarded} баллов`
                  : result.cashback_rub != null
                    ? `Кешбэк ${result.cashback_rub} ₽`
                    : 'Кешбэк начислен на баллы'}
            </Text>
          </View>
        ) : null}

        <Text style={styles.sectionTitle}>Что можно выиграть</Text>
        {prizes.map((prize) => (
          <View key={prize.id} style={styles.sectorRow}>
            <View style={[styles.sectorDot, { backgroundColor: prize.color }]}>
              <Text style={styles.sectorEmoji}>{prize.emoji}</Text>
            </View>
            <View style={styles.sectorCopy}>
              <Text style={styles.sectorTitle}>{prize.title}</Text>
              <Text style={styles.sectorSubtitle}>{prize.subtitle}</Text>
            </View>
            <Text style={styles.sectorType}>{prizeTypeLabel(prize.type)}</Text>
          </View>
        ))}

        <Text style={styles.sectionTitle}>История купонов</Text>
        {couponTx.length === 0 ? (
          <Text style={styles.empty}>
            Пока нет операций — купоны появятся за каждую 1000 ₽ покупок и за рефералов.
          </Text>
        ) : couponTx.map((item) => (
          <CouponTxRow key={item.id} item={item} />
        ))}

        <Text style={styles.sectionTitle}>Последние крутки</Text>
        {history.length === 0 ? (
          <Text style={styles.empty}>Ещё не крутили — первая долька ждёт купон.</Text>
        ) : history.map((item) => (
          <View key={item.id} style={styles.historyRow}>
            <View style={styles.historyCopy}>
              <Text style={styles.historyTitle}>{item.prize_label}</Text>
              <Text style={styles.historyMeta}>{formatWinTime(item.created_at)}</Text>
            </View>
            <Text style={styles.historyType}>{prizeTypeLabel(item.prize_type)}</Text>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFDF8' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 10,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: BORDER,
  },
  backBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  backBtnText: { fontSize: 22, color: DARK_GREEN, fontWeight: '700' },
  headerTitle: { color: DARK_GREEN, fontSize: 18, fontWeight: '900' },
  body: { flex: 1 },
  bodyContent: { paddingHorizontal: 18, paddingBottom: 36, paddingTop: 16, gap: 12 },
  lead: { color: MUTED, fontSize: 13, lineHeight: 18 },
  couponCard: {
    alignItems: 'center',
    backgroundColor: '#FFF3E0',
    borderRadius: 16,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  couponValue: { color: ORANGE, fontSize: 32, fontWeight: '900', lineHeight: 36 },
  couponLabel: { color: '#8A4B12', fontSize: 13, fontWeight: '700' },
  couponHint: { color: MUTED, fontSize: 11, marginTop: 4, textAlign: 'center' },
  loader: { marginVertical: 48 },
  wheelWrap: { alignItems: 'center', paddingVertical: 8 },
  empty: { color: MUTED, fontSize: 13, lineHeight: 18 },
  spinButton: {
    height: 52,
    borderRadius: 16,
    backgroundColor: ORANGE,
    alignItems: 'center',
    justifyContent: 'center',
  },
  spinButtonDisabled: { opacity: 0.45 },
  spinButtonText: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' },
  error: { color: '#C74335', fontSize: 12, textAlign: 'center' },
  resultCard: {
    backgroundColor: '#F2F8DF',
    borderRadius: 16,
    padding: 14,
    gap: 4,
  },
  resultEyebrow: { color: GREEN, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' },
  resultTitle: { color: TEXT, fontSize: 18, fontWeight: '900' },
  resultText: { color: MUTED, fontSize: 13, lineHeight: 18 },
  sectionTitle: { color: DARK_GREEN, fontSize: 16, fontWeight: '900', marginTop: 8 },
  sectorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: BORDER,
  },
  sectorDot: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sectorEmoji: { fontSize: 16 },
  sectorCopy: { flex: 1, gap: 2 },
  sectorTitle: { color: TEXT, fontSize: 14, fontWeight: '800' },
  sectorSubtitle: { color: MUTED, fontSize: 12, lineHeight: 16 },
  sectorType: { color: ORANGE, fontSize: 11, fontWeight: '700' },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 8,
  },
  historyCopy: { flex: 1, gap: 2 },
  historyTitle: { color: TEXT, fontSize: 14, fontWeight: '700' },
  historyMeta: { color: MUTED, fontSize: 11 },
  historyType: { color: DARK_GREEN, fontSize: 11, fontWeight: '700' },
  couponTxRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: BORDER,
  },
  couponTxAmount: { fontSize: 16, fontWeight: '800' },
  couponTxEarn: { color: GREEN },
  couponTxSpend: { color: '#C74335' },
});
