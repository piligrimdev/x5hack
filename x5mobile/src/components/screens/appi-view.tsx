import { useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Keyboard,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PersonalChallenges } from '@/components/screens/personal-sections';
import type { BasketState } from '@/hooks/useBasket';
import { useChallenges } from '@/hooks/useChallenges';
import { useMonthlyEconomy } from '@/hooks/useMonthlyEconomy';
import { useVibes, type Vibe } from '@/hooks/useVibes';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

interface AppiViewProps {
  token: string;
  basket: BasketState;
  onOpenBasket: () => void;
  onChallenges: () => void;
}

function vibeEmoji(vibe: Vibe): string {
  const value = `${vibe.name} ${vibe.description}`.toLowerCase();
  if (value.includes('здоров') || value.includes('пп')) return '🥗';
  if (value.includes('готов') || value.includes('быстр')) return '🍱';
  if (value.includes('коф')) return '☕';
  if (value.includes('сем')) return '🛍️';
  if (value.includes('эконом')) return '🛒';
  if (value.includes('необыч') || value.includes('нов')) return '🍝';
  return '🍽️';
}

function mascotState(saved: number, streak: number): string {
  if (streak >= 2) return `${streak}-й месяц подряд экономите больше. Так держать!`;
  if (saved > 0) return `В этом месяце уже −${Math.round(saved).toLocaleString('ru-RU')} ₽. Аппи найдёт ещё выгоду.`;
  return 'Аппи следит за ценами и заданиями, чтобы вы экономили каждый месяц.';
}

export function AppiView({
  token,
  basket,
  onOpenBasket,
  onChallenges,
}: AppiViewProps) {
  const insets = useSafeAreaInsets();
  const { vibes, selectedVibeId, loading: vibesLoading, saving, error, saveVibe } = useVibes(token);
  const { monthlyEconomy, loading: economyLoading } = useMonthlyEconomy(token);
  const { current, history, loading: challengesLoading } = useChallenges(token);
  const [query, setQuery] = useState('');
  const [vibeModalOpen, setVibeModalOpen] = useState(false);

  const months = monthlyEconomy?.months ?? [];
  const maxSaved = Math.max(...months.map(month => month.saved), 1);
  const currentSaved = monthlyEconomy?.currentMonthSaved ?? 0;
  const previousSaved = monthlyEconomy?.previousMonthSaved ?? 0;
  const cashbackSaved = monthlyEconomy?.currentMonthCashbackRub ?? 0;
  const monthBase = monthlyEconomy?.currentMonthBase ?? 0;
  const betterThanLast = currentSaved > previousSaved;
  const savedSharePct = monthBase > 0 ? Math.round((currentSaved / monthBase) * 100) : 0;
  const selectedVibe = vibes.find(vibe => vibe.id === selectedVibeId) ?? null;
  const completedCount = history.filter(item =>
    item.status === 'выполнено' || item.status === 'completed' || item.status === 'done',
  ).length;
  const activeCount = current.length;

  async function submitBasketRequest(text = query) {
    const request = text.trim();
    if (!request || basket.loading || !basket.hydrated) return;
    Keyboard.dismiss();
    const applied = await basket.sendInstruction(request);
    if (applied) {
      setQuery('');
      onOpenBasket();
    }
  }

  async function chooseVibe(vibeId: string | null) {
    const ok = await saveVibe(vibeId);
    if (ok) setVibeModalOpen(false);
  }

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 12 }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>

        <View style={styles.dashboard}>
          <View style={styles.chartCard}>
            <Text style={styles.chartTitle}>Экономия по месяцам</Text>
            {economyLoading ? (
              <ActivityIndicator color={GREEN} style={styles.chartLoader} />
            ) : (
              <>
                <View style={styles.chartBars}>
                  {months.map((month, index) => (
                    <View key={month.key} style={styles.chartCol}>
                      <Text style={styles.chartValue}>
                        {month.saved > 0 ? Math.round(month.saved).toLocaleString('ru-RU') : '—'}
                      </Text>
                      <View
                        style={[
                          styles.chartBar,
                          {
                            height: Math.max(10, (month.saved / maxSaved) * 120),
                            backgroundColor: index === months.length - 1 ? GREEN : '#DCE8DE',
                          },
                        ]}
                      />
                      <Text style={styles.chartLabel}>{month.label}</Text>
                    </View>
                  ))}
                </View>
                <View style={styles.chartSummary}>
                  <View style={styles.summaryItem}>
                    <Text style={[styles.summaryValue, betterThanLast ? styles.summaryGood : styles.summaryNeutral]}>
                      {previousSaved === 0 && currentSaved === 0
                        ? 'нет данных'
                        : betterThanLast
                          ? 'лучше прошлого'
                          : currentSaved === previousSaved
                            ? 'как в прошлом'
                            : 'слабее прошлого'}
                    </Text>
                    <Text style={styles.summaryCaption}>сравнение с прошлым месяцем</Text>
                  </View>
                  <View style={styles.summaryItem}>
                    <Text style={styles.summaryValue}>{cashbackSaved.toLocaleString('ru-RU')} ₽</Text>
                    <Text style={styles.summaryCaption}>сэкономлено кешбеком</Text>
                  </View>
                  <View style={styles.summaryItem}>
                    <Text style={styles.summaryValue}>{savedSharePct}%</Text>
                    <Text style={styles.summaryCaption}>от всех покупок</Text>
                  </View>
                </View>
              </>
            )}
          </View>

          <View style={styles.mascotCard}>
            <Image
              source={require('../../../assets/images/mascot.png')}
              style={styles.mascot}
              resizeMode="contain"
            />
            <Text style={styles.mascotState}>
              {mascotState(currentSaved, monthlyEconomy?.consecutiveGrowthMonths ?? 0)}
            </Text>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <View style={styles.sectionCopy}>
              <Text style={styles.sectionTitle}>Задания</Text>
              <Text style={styles.sectionDescription}>
                Персональные цели от Аппи: закрывайте пункты в покупках и получайте баллы.
              </Text>
            </View>
            <View style={styles.statsBadge}>
              {challengesLoading ? (
                <ActivityIndicator color={GREEN} size="small" />
              ) : (
                <>
                  <Text style={styles.statsValue}>{activeCount}</Text>
                  <Text style={styles.statsLabel}>активных</Text>
                  <Text style={styles.statsHint}>{completedCount} закрыто</Text>
                </>
              )}
            </View>
          </View>
          <PersonalChallenges token={token} onDetails={onChallenges} limit={4} showHeading={false} />
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Ваш вайб</Text>
          <Text style={styles.sectionDescription}>
            Направление, по которому Аппи подбирает задания и собирает корзину.
          </Text>
          <View style={styles.vibeRow}>
            <View style={styles.vibeInfo}>
              {vibesLoading ? (
                <ActivityIndicator color={GREEN} />
              ) : selectedVibe ? (
                <>
                  <Text style={styles.vibeName}>
                    {vibeEmoji(selectedVibe)} {selectedVibe.name}
                  </Text>
                  <Text style={styles.vibeText}>{selectedVibe.description}</Text>
                </>
              ) : (
                <>
                  <Text style={styles.vibeName}>Вайб не выбран</Text>
                  <Text style={styles.vibeText}>Выберите направление — Аппи начнёт учитывать его в рекомендациях.</Text>
                </>
              )}
            </View>
            <TouchableOpacity
              style={styles.vibeButton}
              onPress={() => setVibeModalOpen(true)}
              activeOpacity={0.8}>
              <Text style={styles.vibeButtonText}>{selectedVibe ? 'Поменять' : 'Выбрать'}</Text>
            </TouchableOpacity>
          </View>
          {error ? <Text style={styles.inlineError}>Не удалось загрузить или сохранить вайб</Text> : null}
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Корзина с Аппи</Text>
          <Text style={styles.sectionDescription}>
            Напишите, что нужно собрать — Аппи подберёт товары с учётом вайба и вашей истории.
          </Text>
          <View style={styles.basketRow}>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Собрать корзину с Аппи"
              placeholderTextColor="#8B8F8B"
              style={styles.basketInput}
              returnKeyType="send"
              editable={!basket.loading}
              onSubmitEditing={() => submitBasketRequest()}
            />
            <TouchableOpacity
              style={[styles.sendButton, (!query.trim() || basket.loading) && styles.sendButtonDisabled]}
              onPress={() => submitBasketRequest()}
              activeOpacity={0.8}
              disabled={!query.trim() || basket.loading}>
              {basket.loading
                ? <ActivityIndicator color="#FFFFFF" size="small" />
                : <Text style={styles.sendButtonText}>Отправить</Text>}
            </TouchableOpacity>
          </View>
          {basket.message ? <Text style={styles.basketMessage}>{basket.message}</Text> : null}
        </View>
      </ScrollView>

      <Modal
        visible={vibeModalOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setVibeModalOpen(false)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setVibeModalOpen(false)}>
          <Pressable style={[styles.modalCard, { paddingBottom: insets.bottom + 18 }]} onPress={() => {}}>
            <Text style={styles.modalTitle}>Выберите вайб</Text>
            <Text style={styles.modalSubtitle}>На кнопке — название и описание направления</Text>
            <ScrollView style={styles.modalList} showsVerticalScrollIndicator={false}>
              {vibes.map(vibe => {
                const selected = selectedVibeId === vibe.id;
                return (
                  <TouchableOpacity
                    key={vibe.id}
                    style={[styles.vibeOption, selected && styles.vibeOptionSelected]}
                    onPress={() => chooseVibe(vibe.id)}
                    disabled={saving}
                    activeOpacity={0.8}>
                    <Text style={styles.vibeOptionEmoji}>{vibeEmoji(vibe)}</Text>
                    <View style={styles.vibeOptionCopy}>
                      <Text style={styles.vibeOptionName}>{vibe.name}</Text>
                      <Text style={styles.vibeOptionDescription}>{vibe.description}</Text>
                    </View>
                  </TouchableOpacity>
                );
              })}
              <TouchableOpacity
                style={styles.resetOption}
                onPress={() => chooseVibe(null)}
                disabled={saving}
                activeOpacity={0.8}>
                <Text style={styles.resetOptionText}>Сбросить вайб</Text>
              </TouchableOpacity>
            </ScrollView>
            {saving ? <ActivityIndicator color={GREEN} style={{ marginTop: 10 }} /> : null}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 18, paddingBottom: 28, gap: 18 },

  dashboard: { flexDirection: 'row', gap: 10, alignItems: 'stretch' },
  chartCard: {
    flex: 1,
    backgroundColor: '#F7F8F6',
    borderRadius: 18,
    padding: 14,
    minHeight: 248,
  },
  chartTitle: { color: DARK_GREEN, fontSize: 15, fontWeight: '800' },
  chartLoader: { marginVertical: 48 },
  chartBars: { height: 156, flexDirection: 'row', alignItems: 'flex-end', gap: 8, marginTop: 12 },
  chartCol: { flex: 1, alignItems: 'center', justifyContent: 'flex-end', gap: 4 },
  chartValue: { color: MUTED, fontSize: 9, fontWeight: '700' },
  chartBar: { width: '100%', borderRadius: 7 },
  chartLabel: { textAlign: 'center', color: MUTED, fontSize: 11, fontWeight: '600' },
  chartSummary: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: BORDER,
  },
  summaryItem: { flex: 1, gap: 3 },
  summaryValue: { color: TEXT, fontSize: 12, fontWeight: '800', lineHeight: 15 },
  summaryGood: { color: GREEN },
  summaryNeutral: { color: TEXT },
  summaryCaption: { color: MUTED, fontSize: 10, lineHeight: 13 },
  mascotCard: {
    width: 108,
    borderRadius: 18,
    backgroundColor: '#FFF6EC',
    paddingHorizontal: 8,
    paddingTop: 8,
    paddingBottom: 10,
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  mascot: { width: 88, height: 110 },
  mascotState: { color: '#5C564E', fontSize: 10, lineHeight: 13, textAlign: 'center' },

  section: { gap: 8 },
  sectionHeader: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  sectionCopy: { flex: 1, gap: 4 },
  sectionTitle: { color: DARK_GREEN, fontSize: 20, fontWeight: '900' },
  sectionDescription: { color: MUTED, fontSize: 13, lineHeight: 18 },
  statsBadge: {
    minWidth: 78,
    borderRadius: 14,
    backgroundColor: '#F2F8DF',
    paddingHorizontal: 10,
    paddingVertical: 8,
    alignItems: 'center',
  },
  statsValue: { color: GREEN, fontSize: 20, fontWeight: '900', lineHeight: 22 },
  statsLabel: { color: DARK_GREEN, fontSize: 10, fontWeight: '700' },
  statsHint: { color: MUTED, fontSize: 9, marginTop: 2 },

  vibeRow: {
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 16,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  vibeInfo: { flex: 1, gap: 4 },
  vibeName: { color: TEXT, fontSize: 15, fontWeight: '800' },
  vibeText: { color: MUTED, fontSize: 12, lineHeight: 17 },
  vibeButton: {
    borderWidth: 1,
    borderColor: GREEN,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    minWidth: 92,
    alignItems: 'center',
  },
  vibeButtonText: { color: GREEN, fontSize: 13, fontWeight: '800' },
  inlineError: { color: '#C74335', fontSize: 11 },

  basketRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  basketInput: {
    flex: 1,
    minHeight: 52,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: BORDER,
    paddingHorizontal: 16,
    color: TEXT,
    fontSize: 14,
    backgroundColor: '#FFFFFF',
  },
  sendButton: {
    height: 48,
    borderRadius: 12,
    backgroundColor: GREEN,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: { opacity: 0.45 },
  sendButtonText: { color: '#FFFFFF', fontSize: 13, fontWeight: '800' },
  basketMessage: { color: MUTED, fontSize: 11 },

  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(23,23,26,0.45)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    paddingHorizontal: 18,
    paddingTop: 18,
    maxHeight: '82%',
  },
  modalTitle: { color: DARK_GREEN, fontSize: 20, fontWeight: '900' },
  modalSubtitle: { color: MUTED, fontSize: 13, marginTop: 4, marginBottom: 12 },
  modalList: { maxHeight: 460 },
  vibeOption: {
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 14,
    padding: 12,
    flexDirection: 'row',
    gap: 10,
    marginBottom: 8,
    backgroundColor: '#FFFFFF',
  },
  vibeOptionSelected: { borderColor: GREEN, backgroundColor: '#F7FCF8' },
  vibeOptionEmoji: { fontSize: 28 },
  vibeOptionCopy: { flex: 1, gap: 3 },
  vibeOptionName: { color: TEXT, fontSize: 15, fontWeight: '800' },
  vibeOptionDescription: { color: MUTED, fontSize: 12, lineHeight: 17 },
  resetOption: { alignItems: 'center', paddingVertical: 12 },
  resetOptionText: { color: GREEN, fontSize: 13, fontWeight: '700' },
});
