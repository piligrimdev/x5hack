import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BasketItem, BasketState } from '@/hooks/useBasket';
import { isBasketChallenge, type ChallengeItem, useChallenges } from '@/hooks/useChallenges';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

interface SavingsViewProps {
  onOrderPlaced: () => void;
  basket: BasketState;
  token: string;
}

export function SavingsView({ onOrderPlaced, basket, token }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
  const {
    current: challenges,
    loading: challengesLoading,
    error: challengesError,
    refetch: refetchChallenges,
  } = useChallenges(token, true);
  const {
    items: basketItems,
    loading: basketLoading,
    message: basketMessage,
    sendInstruction,
    checkout,
    preview,
    spendPoints,
    setSpendPoints,
    hasCollected,
    hydrated,
    collectWeeklyBasket,
  } = basket;
  const [instructionText, setInstructionText] = useState('');

  function handleSendInstruction() {
    const text = instructionText.trim();
    if (!text) return;
    sendInstruction(text);
    setInstructionText('');
  }

  async function handleCheckout() {
    if (!(await checkout())) return;
    onOrderPlaced();

    // Receipt processing happens in the background. Refresh a few times so
    // the tracker reflects progress/completion and the replacement challenge
    // instead of staying on the pre-checkout snapshot.
    for (const delayMs of [500, 1000, 1500]) {
      await new Promise(resolve => setTimeout(resolve, delayMs));
      await refetchChallenges();
    }
  }

  const pricedItems = basketItems.map((item: BasketItem) => {
    const previewItem = preview?.items.find((p) => p.product_id === item.product_id);
    const unitPaid = previewItem?.paid_price ?? item.price;
    const unitBase = previewItem?.base_price ?? item.price;
    return { item, unitPaid, unitBase, lineTotal: Math.round(unitPaid * item.quantity) };
  });
  const roundedItemsTotal = pricedItems.reduce((sum, p) => sum + p.lineTotal, 0);

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 12 }]}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled">

        <Text style={styles.pageEyebrow}>Корзина</Text>
        <Text style={styles.pageDescription}>
          Товары на неделю: Аппи подберёт их с учётом вайба и вашей истории.
        </Text>

        <View style={styles.basketCard}>
          {!hydrated ? (
            <ActivityIndicator color={MUTED} />
          ) : basketLoading && basketItems.length === 0 ? (
            <View style={styles.basketCollectBlock}>
              <ActivityIndicator color={GREEN} />
              <Text style={styles.basketEmptyText}>Аппи собирает корзину на неделю…</Text>
            </View>
          ) : basketItems.length > 0 ? (
            pricedItems.map(({ item, unitBase, lineTotal }) => {
              const hasDiscount = lineTotal < Math.round(unitBase * item.quantity);
              return (
                <View key={item.product_id} style={styles.basketRow}>
                  <View style={styles.basketItemInfo}>
                    <Text style={styles.basketItemName}>{item.name}</Text>
                    <Text style={styles.basketItemQty}>{item.quantity} шт</Text>
                  </View>
                  <View style={styles.basketItemPrices}>
                    {hasDiscount && (
                      <Text style={styles.basketItemBasePrice}>{Math.round(unitBase * item.quantity)} ₽</Text>
                    )}
                    <Text style={styles.basketItemPaidPrice}>{lineTotal} ₽</Text>
                  </View>
                </View>
              );
            })
          ) : (
            <View style={styles.basketCollectBlock}>
              <Text style={styles.basketEmptyText}>
                {hasCollected
                  ? 'Корзина пуста — попросите Аппи собрать новую'
                  : 'Аппи подберёт продукты на неделю с учётом ваших покупок'}
              </Text>
              <TouchableOpacity
                style={[styles.collectBtn, basketLoading && styles.collectBtnDisabled]}
                onPress={collectWeeklyBasket}
                activeOpacity={0.7}
                disabled={basketLoading}>
                {basketLoading
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={styles.collectBtnText}>Собрать корзину на неделю</Text>
                }
              </TouchableOpacity>
            </View>
          )}

          {basketMessage && <Text style={styles.basketMessage}>{basketMessage}</Text>}

          <Text style={styles.appiLabel}>Спроси Аппи</Text>
          <View style={styles.basketInputRow}>
            <TextInput
              style={styles.basketInput}
              placeholder="Например: добавь молоко"
              placeholderTextColor={MUTED}
              value={instructionText}
              onChangeText={setInstructionText}
              editable={!basketLoading}
              returnKeyType="send"
              onSubmitEditing={handleSendInstruction}
            />
            <TouchableOpacity
              style={[styles.basketSendBtn, (basketLoading || !instructionText.trim()) && styles.basketSendBtnDisabled]}
              onPress={handleSendInstruction}
              activeOpacity={0.7}
              disabled={basketLoading || !instructionText.trim()}>
              {basketLoading
                ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={styles.basketSendBtnText}>→</Text>
              }
            </TouchableOpacity>
          </View>

          {preview && basketItems.length > 0 && (
            <View style={styles.basketTotals}>
              <View style={styles.basketTotalsRow}>
                <Text style={styles.basketTotalsLabel}>Итого</Text>
                <Text style={styles.basketTotalsValue}>
                  {spendPoints && preview.cashback && preview.cashback.cashback_rub > 0
                    ? Math.round(preview.cashback.total_paid_rub)
                    : roundedItemsTotal} ₽
                </Text>
              </View>
              {preview.total_base > preview.total_paid && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Скидка</Text>
                  <Text style={styles.basketTotalsDiscount}>
                    −{Math.round(preview.total_base - preview.total_paid)} ₽
                  </Text>
                </View>
              )}
              {preview.cashback && preview.cashback.points_available > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>
                    Списать баллы ({preview.cashback.points_available})
                  </Text>
                  <Switch
                    value={spendPoints}
                    onValueChange={setSpendPoints}
                    trackColor={{ false: BORDER, true: GREEN }}
                  />
                </View>
              )}
              {spendPoints && preview.cashback && preview.cashback.cashback_rub > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Баллами</Text>
                  <Text style={styles.basketTotalsDiscount}>
                    −{preview.cashback.cashback_rub} ₽
                  </Text>
                </View>
              )}
            </View>
          )}

          <TouchableOpacity
            style={[styles.checkoutBtn, (basketLoading || basketItems.length === 0) && styles.checkoutBtnDisabled]}
            onPress={handleCheckout}
            activeOpacity={0.7}
            disabled={basketLoading || basketItems.length === 0}>
            {basketLoading
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.checkoutBtnText}>Оформить заказ</Text>
            }
          </TouchableOpacity>
        </View>

        <Text style={styles.sectionTitle}>Задания</Text>
        <View style={styles.challengeList}>
          {challengesLoading && challenges.length === 0 && (
            <ActivityIndicator color={GREEN} />
          )}
          {!challengesLoading && challengesError && (
            <Text style={styles.challengeMessage}>Не удалось загрузить задания</Text>
          )}
          {!challengesLoading && !challengesError && challenges.length === 0 && (
            <Text style={styles.challengeMessage}>Нет активных заданий</Text>
          )}
          {challenges.map(challenge => (
            <BasketChallengeCard key={challenge.id} challenge={challenge} />
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

function BasketChallengeCard({ challenge }: { challenge: ChallengeItem }) {
  const done = challenge.status === 'выполнено' || challenge.status === 'completed' || challenge.status === 'done';
  const current = done
    ? challenge.quantity_target
    : isBasketChallenge(challenge)
      ? 0
      : challenge.quantity_current;
  const progress = Math.min(100, Math.round((current / challenge.quantity_target) * 100));

  return (
    <View style={[styles.challengeCard, done && styles.challengeCardDone]}>
      <View style={styles.challengeTopRow}>
        <View style={styles.challengeText}>
          <Text style={[styles.challengeTitle, done && styles.challengeTitleDone]}>{challenge.title}</Text>
          <Text style={styles.challengeDescription}>{challenge.description}</Text>
        </View>
        {done ? (
          <View style={styles.challengeDoneCircle}>
            <Text style={styles.challengeDoneCheck}>✓</Text>
          </View>
        ) : (
          <View style={styles.challengeProgressPill}>
            <Text style={styles.challengeProgressText}>
              {current}/{challenge.quantity_target}
            </Text>
          </View>
        )}
      </View>
      <View style={styles.challengeProgressTrack}>
        <View style={[styles.challengeProgressFill, done && styles.challengeProgressFillDone, { width: `${progress}%` as `${number}%` }]} />
      </View>
      <View style={styles.challengeFooter}>
        <Text style={[styles.challengeReward, done && styles.challengeRewardDone]}>
          {done ? 'Выполнено' : `+${challenge.reward_rub} баллов`}
        </Text>
        <Text style={styles.challengeDeadline}>
          до {new Date(challenge.deadline).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 18, paddingBottom: 28, gap: 12 },
  pageEyebrow: { color: DARK_GREEN, fontSize: 22, fontWeight: '900' },
  pageDescription: { color: MUTED, fontSize: 13, lineHeight: 18, marginBottom: 4 },
  sectionTitle: { color: TEXT, fontSize: 18, fontWeight: '900', marginTop: 8 },
  basketCard: {
    backgroundColor: '#F7F8F6',
    borderRadius: 18,
    padding: 14,
    gap: 10,
  },
  basketRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  basketItemInfo: { flex: 1 },
  basketItemName: { fontSize: 15, fontWeight: '700', color: TEXT },
  basketItemQty: { fontSize: 13, color: MUTED, fontWeight: '600', marginTop: 2 },
  basketItemPrices: { alignItems: 'flex-end' },
  basketItemBasePrice: {
    fontSize: 12,
    color: MUTED,
    textDecorationLine: 'line-through',
  },
  basketItemPaidPrice: { fontSize: 15, fontWeight: '800', color: TEXT },
  basketTotals: {
    borderTopWidth: 1,
    borderTopColor: BORDER,
    paddingTop: 10,
    gap: 6,
  },
  basketTotalsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  basketTotalsLabel: { fontSize: 13, color: MUTED },
  basketTotalsValue: { fontSize: 16, fontWeight: '800', color: TEXT },
  basketTotalsDiscount: { fontSize: 13, fontWeight: '700', color: GREEN },
  basketEmptyText: { fontSize: 13, color: MUTED, lineHeight: 18 },
  basketCollectBlock: { gap: 10, alignItems: 'flex-start' },
  collectBtn: {
    backgroundColor: DARK_GREEN,
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  collectBtnDisabled: { opacity: 0.45 },
  collectBtnText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  basketMessage: { fontSize: 12, color: MUTED, fontStyle: 'italic' },
  appiLabel: { fontSize: 12, fontWeight: '700', color: MUTED, marginTop: 4 },
  basketInputRow: { flexDirection: 'row', gap: 8 },
  basketInput: {
    flex: 1,
    minWidth: 0,
    minHeight: 48,
    backgroundColor: '#FFFFFF',
    borderRadius: 26,
    borderWidth: 1,
    borderColor: BORDER,
    paddingHorizontal: 16,
    fontSize: 14,
    color: TEXT,
  },
  basketSendBtn: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: GREEN,
    alignItems: 'center',
    justifyContent: 'center',
  },
  basketSendBtnDisabled: { opacity: 0.45 },
  basketSendBtnText: { color: '#fff', fontSize: 18, fontWeight: '700' },
  checkoutBtn: {
    backgroundColor: GREEN,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  checkoutBtnDisabled: { backgroundColor: '#D5D8D5' },
  checkoutBtnText: { color: '#fff', fontSize: 15, fontWeight: '800' },
  challengeList: { gap: 10 },
  challengeMessage: { color: MUTED, fontSize: 13, paddingVertical: 12 },
  challengeCard: {
    backgroundColor: '#F7F8F6',
    borderRadius: 16,
    padding: 14,
    gap: 10,
  },
  challengeCardDone: { backgroundColor: '#EAF6ED' },
  challengeTopRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  challengeText: { flex: 1, gap: 4 },
  challengeTitle: { color: TEXT, fontSize: 15, fontWeight: '800' },
  challengeTitleDone: { color: DARK_GREEN },
  challengeDescription: { color: MUTED, fontSize: 12, lineHeight: 17 },
  challengeProgressPill: {
    backgroundColor: '#E7EFE9',
    borderRadius: 100,
    paddingVertical: 4,
    paddingHorizontal: 9,
  },
  challengeProgressText: { color: DARK_GREEN, fontSize: 12, fontWeight: '800' },
  challengeDoneCircle: {
    width: 25,
    height: 25,
    borderRadius: 13,
    backgroundColor: GREEN,
    alignItems: 'center',
    justifyContent: 'center',
  },
  challengeDoneCheck: { color: '#fff', fontSize: 15, fontWeight: '900' },
  challengeProgressTrack: {
    height: 7,
    borderRadius: 100,
    backgroundColor: '#E1E5E1',
    overflow: 'hidden',
  },
  challengeProgressFill: { height: 7, borderRadius: 100, backgroundColor: GREEN },
  challengeProgressFillDone: { backgroundColor: GREEN },
  challengeFooter: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  challengeReward: { color: GREEN, fontSize: 12, fontWeight: '800' },
  challengeRewardDone: { color: DARK_GREEN },
  challengeDeadline: { color: MUTED, fontSize: 11 },
});
