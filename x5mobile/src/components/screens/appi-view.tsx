import { useState } from 'react';
import {
  ActivityIndicator,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import Animated, { FadeIn, ZoomIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { FortuneWheel, type SpinRequest } from '@/components/screens/fortune-wheel';
import {
  formatWinTime,
  prizeTypeLabel,
  useFortuneWheel,
  type FortunePrize,
} from '@/hooks/useFortuneWheel';

const ORANGE = '#FF6D00';
const GREEN = '#25A244';
const GREEN_BANNER = '#1B5E35';

interface AppiViewProps {
  token: string;
  onChallenges: () => void;
}

export function AppiView({ token, onChallenges }: AppiViewProps) {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const { snapshot, loading, spin } = useFortuneWheel(token);

  const [phase, setPhase] = useState<'idle' | 'spinning' | 'result'>('idle');
  const [wonPrize, setWonPrize] = useState<FortunePrize | null>(null);
  const [spinRequest, setSpinRequest] = useState<SpinRequest | null>(null);

  const wheelSize = Math.min(300, Math.max(240, width - 72));
  const spinsLeft = snapshot?.spinsLeft ?? 0;
  const canSpin = phase === 'idle' && spinsLeft > 0;

  async function handleSpin() {
    if (!snapshot || !canSpin) return;
    setPhase('spinning');
    try {
      const prize = await spin();
      const targetIndex = snapshot.prizes.findIndex((item) => item.id === prize.id);
      setWonPrize(prize);
      setSpinRequest({
        targetIndex: targetIndex >= 0 ? targetIndex : 0,
        nonce: Date.now(),
      });
    } catch {
      setPhase('idle');
    }
  }

  function handleSpinComplete() {
    setPhase('result');
  }

  function dismissResult() {
    setWonPrize(null);
    setPhase('idle');
  }

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <View>
          <Text style={styles.headerTitle}>Аппи</Text>
          <Text style={styles.headerSub}>Крути колесо — я уже выбрал призы</Text>
        </View>
        <View style={styles.spinsBadge}>
          <Text style={styles.spinsBadgeValue}>{spinsLeft}</Text>
          <Text style={styles.spinsBadgeLabel}>крутки</Text>
        </View>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <View style={styles.heroText}>
            <Text style={styles.heroTitle}>Колесо фортуны</Text>
            <Text style={styles.heroSub}>
              Кешбэк, скидки и подарки.{'\n'}
              {snapshot
                ? `${snapshot.spinsPerDay} крутки в день — успей забрать`
                : 'Загружаю призы…'}
            </Text>
          </View>
          <Image
            source={require('../../../assets/images/mascot.png')}
            style={styles.mascot}
            resizeMode="contain"
          />
        </View>

        <View style={styles.wheelCard}>
          {loading || !snapshot ? (
            <ActivityIndicator color={ORANGE} style={{ marginVertical: 80 }} />
          ) : (
            <>
              <FortuneWheel
                prizes={snapshot.prizes}
                size={wheelSize}
                spinRequest={spinRequest}
                onSpinComplete={handleSpinComplete}
              />
              <TouchableOpacity
                style={[styles.spinBtn, !canSpin && styles.spinBtnDisabled]}
                onPress={handleSpin}
                activeOpacity={0.85}
                disabled={!canSpin}>
                <Text style={styles.spinBtnText}>
                  {phase === 'spinning'
                    ? 'Крутится…'
                    : spinsLeft > 0
                      ? 'Крутить'
                      : 'Крутки закончились'}
                </Text>
              </TouchableOpacity>
              {spinsLeft === 0 && phase === 'idle' ? (
                <TouchableOpacity onPress={onChallenges} activeOpacity={0.7}>
                  <Text style={styles.earnMore}>Выполни задание — получи крутку ›</Text>
                </TouchableOpacity>
              ) : (
                <Text style={styles.resetHint}>Новые крутки — каждый день</Text>
              )}
            </>
          )}
        </View>

        {snapshot && (
          <>
            <Text style={styles.sectionTitle}>Призы на колесе</Text>
            <View style={styles.prizeGrid}>
              {snapshot.prizes.map((prize) => (
                <View key={prize.id} style={styles.prizeChip}>
                  <View style={[styles.prizeDot, { backgroundColor: prize.color }]} />
                  <Text style={styles.prizeEmoji}>{prize.emoji}</Text>
                  <View style={styles.prizeChipText}>
                    <Text style={styles.prizeChipTitle}>{prize.title}</Text>
                    <Text style={styles.prizeChipType}>{prizeTypeLabel(prize.type)}</Text>
                  </View>
                </View>
              ))}
            </View>

            <Text style={styles.sectionTitle}>Недавние выигрыши</Text>
            <View style={styles.historyCard}>
              {snapshot.history.length === 0 ? (
                <Text style={styles.emptyHistory}>Пока пусто — сделай первую крутку</Text>
              ) : (
                snapshot.history.slice(0, 6).map((win, index, list) => (
                  <View
                    key={win.id}
                    style={[styles.historyRow, index < list.length - 1 && styles.historyRowBorder]}>
                    <Text style={styles.historyEmoji}>{win.prize.emoji}</Text>
                    <View style={styles.historyInfo}>
                      <Text style={styles.historyTitle}>{win.prize.title}</Text>
                      <Text style={styles.historyMeta}>
                        {prizeTypeLabel(win.prize.type)} · {formatWinTime(win.wonAt)}
                      </Text>
                    </View>
                  </View>
                ))
              )}
            </View>
          </>
        )}
      </ScrollView>

      {phase === 'result' && wonPrize && (
        <TouchableOpacity style={styles.overlay} activeOpacity={1} onPress={dismissResult}>
          <Animated.View entering={FadeIn.duration(180)} style={StyleSheet.absoluteFill} />
          <Animated.View entering={ZoomIn.duration(280)} style={styles.resultCard}>
            <Text style={styles.resultEyebrow}>{prizeTypeLabel(wonPrize.type)}</Text>
            <Text style={styles.resultEmoji}>{wonPrize.emoji}</Text>
            <Text style={styles.resultTitle}>{wonPrize.title}</Text>
            <Text style={styles.resultSub}>{wonPrize.subtitle}</Text>
            <TouchableOpacity style={styles.resultBtn} onPress={dismissResult} activeOpacity={0.85}>
              <Text style={styles.resultBtnText}>Забрать</Text>
            </TouchableOpacity>
          </Animated.View>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#F5F5F2' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 12,
  },
  headerTitle: { fontSize: 22, fontWeight: '800', color: '#17171A' },
  headerSub: { fontSize: 13, color: '#8A8A8E', marginTop: 2 },
  spinsBadge: {
    backgroundColor: '#FFF3E0',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 6,
    alignItems: 'center',
    minWidth: 64,
  },
  spinsBadgeValue: { fontSize: 18, fontWeight: '800', color: ORANGE, lineHeight: 22 },
  spinsBadgeLabel: { fontSize: 10, fontWeight: '600', color: '#C45A00' },

  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 16, paddingBottom: 28, gap: 12 },

  hero: {
    backgroundColor: GREEN_BANNER,
    borderRadius: 20,
    paddingLeft: 18,
    paddingVertical: 16,
    flexDirection: 'row',
    overflow: 'hidden',
    minHeight: 112,
  },
  heroText: { flex: 1, justifyContent: 'center', gap: 6 },
  heroTitle: { color: '#fff', fontSize: 20, fontWeight: '800' },
  heroSub: { color: 'rgba(255,255,255,0.82)', fontSize: 13, lineHeight: 18 },
  mascot: { width: 110, height: 120, marginRight: -8, marginBottom: -16 },

  wheelCard: {
    backgroundColor: '#fff',
    borderRadius: 20,
    paddingVertical: 16,
    paddingHorizontal: 8,
    alignItems: 'center',
    gap: 14,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.06)',
  },
  spinBtn: {
    backgroundColor: ORANGE,
    borderRadius: 100,
    paddingVertical: 14,
    paddingHorizontal: 48,
    minWidth: 200,
    alignItems: 'center',
  },
  spinBtnDisabled: { backgroundColor: '#C8C7C3' },
  spinBtnText: { color: '#fff', fontSize: 17, fontWeight: '800' },
  earnMore: { fontSize: 14, color: GREEN, fontWeight: '600' },
  resetHint: { fontSize: 12, color: '#8A8A8E' },

  sectionTitle: { fontSize: 18, fontWeight: '800', color: '#17171A', marginTop: 4 },
  prizeGrid: { gap: 8 },
  prizeChip: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.06)',
  },
  prizeDot: { width: 10, height: 10, borderRadius: 5 },
  prizeEmoji: { fontSize: 18 },
  prizeChipText: { flex: 1 },
  prizeChipTitle: { fontSize: 14, fontWeight: '700', color: '#17171A' },
  prizeChipType: { fontSize: 12, color: '#8A8A8E', marginTop: 1 },

  historyCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.06)',
  },
  emptyHistory: {
    fontSize: 14,
    color: '#8A8A8E',
    textAlign: 'center',
    paddingVertical: 20,
  },
  historyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
  },
  historyRowBorder: { borderBottomWidth: 1, borderBottomColor: 'rgba(0,0,0,0.06)' },
  historyEmoji: { fontSize: 22 },
  historyInfo: { flex: 1 },
  historyTitle: { fontSize: 14, fontWeight: '700', color: '#17171A' },
  historyMeta: { fontSize: 12, color: '#8A8A8E', marginTop: 2 },

  overlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(23,23,26,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 28,
    zIndex: 20,
  },
  resultCard: {
    backgroundColor: '#fff',
    borderRadius: 24,
    paddingHorizontal: 24,
    paddingVertical: 28,
    alignItems: 'center',
    width: '100%',
    maxWidth: 340,
    gap: 6,
  },
  resultEyebrow: {
    fontSize: 12,
    fontWeight: '700',
    color: ORANGE,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  resultEmoji: { fontSize: 56, marginVertical: 6 },
  resultTitle: { fontSize: 22, fontWeight: '800', color: '#17171A', textAlign: 'center' },
  resultSub: { fontSize: 14, color: '#8A8A8E', textAlign: 'center', lineHeight: 20, marginBottom: 8 },
  resultBtn: {
    backgroundColor: GREEN,
    borderRadius: 100,
    paddingVertical: 13,
    paddingHorizontal: 36,
    marginTop: 6,
  },
  resultBtnText: { color: '#fff', fontSize: 16, fontWeight: '800' },
});
