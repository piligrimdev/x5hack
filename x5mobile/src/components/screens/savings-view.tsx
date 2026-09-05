import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { BasketItem, useBasket } from '@/hooks/useBasket';
import { ChallengeItem, useChallenges } from '@/hooks/useChallenges';
import { LeaderboardEntry, Savings } from '@/mock-data';

interface SavingsViewProps {
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  token: string;
  goHome: () => void;
  goHistory: () => void;
  goChallenges: () => void;
  onOrderPlaced: () => void;
}

export function SavingsView({ leaderboard, savings, token, goHome, goHistory, goChallenges, onOrderPlaced }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
  const { current: challenges } = useChallenges(token);
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
  } = useBasket(token, onOrderPlaced);
  const [instructionText, setInstructionText] = useState('');

  function handleSendInstruction() {
    const text = instructionText.trim();
    if (!text) return;
    sendInstruction(text);
    setInstructionText('');
  }

  function handleCheckout() {
    checkout();
  }
  const savedAmount = savings.withoutDiscount - savings.paid;
  const savedPct = Math.round((savedAmount / savings.withoutDiscount) * 100);
  const paidPct = (savings.paid / savings.withoutDiscount) * 100;
  const greenPct = (savedAmount / savings.withoutDiscount) * 100;
  const pricedItems = basketItems.map((item: BasketItem) => {
    const previewItem = preview?.items.find((p) => p.product_id === item.product_id);
    const unitPaid = previewItem?.paid_price ?? item.price;
    const unitBase = previewItem?.base_price ?? item.price;
    return { item, unitPaid, unitBase, lineTotal: Math.round(unitPaid * item.quantity) };
  });
  const roundedItemsTotal = pricedItems.reduce((sum, p) => sum + p.lineTotal, 0);

  return (
    <View style={styles.root}>
      {/* Dark header */}
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <TouchableOpacity style={styles.backBtn} onPress={goHome} activeOpacity={0.7}>
          <Text style={styles.backBtnText}>←</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Экономия</Text>
        <View style={styles.headerRight}>
          <TouchableOpacity style={styles.iconBtn} onPress={goChallenges} activeOpacity={0.7}>
            <Text style={styles.backBtnText}>📋</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.iconBtn} onPress={goHistory} activeOpacity={0.7}>
            <Text style={styles.backBtnText}>🕐</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled">

        {/* Savings card */}
        <View style={styles.card}>
          <View style={styles.cardHeaderRow}>
            <Text style={styles.cardHeaderLabel}>ЭКОНОМИЯ ЗА НЕДЕЛЮ</Text>
            <View style={styles.savedBadge}>
              <Text style={styles.savedBadgeText}>−{savedAmount} ₽ ({savedPct}%)</Text>
            </View>
          </View>

          {/* Progress bar: сначала серый (потрачено), потом зелёный (сэкономлено) */}
          <View style={styles.progressBarTrack}>
            <View style={[styles.progressBarGray, { width: `${paidPct}%` as `${number}%` }]} />
            <View style={[styles.progressBarGreen, { width: `${greenPct}%` as `${number}%` }]} />
          </View>

          {/* Legend */}
          <View style={styles.legendRow}>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: BrandColors.textSecondary }]} />
              <Text style={styles.legendText}>Потрачено {savings.paid.toLocaleString('ru')} ₽</Text>
            </View>
            <View style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: BrandColors.green }]} />
              <Text style={styles.legendText}>Сэкономлено {savedAmount} ₽</Text>
            </View>
          </View>
        </View>

        {/* Weekly basket */}
        <Text style={styles.sectionTitle}>Корзина на неделю</Text>
        <View style={styles.basketCard}>
          {!hydrated ? (
            <ActivityIndicator color={BrandColors.textSecondary} />
          ) : basketLoading && basketItems.length === 0 ? (
            <ActivityIndicator color={BrandColors.textSecondary} />
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
          ) : !basketMessage?.startsWith('Заказ оформлен') ? (
            <View style={styles.basketCollectBlock}>
              <Text style={styles.basketEmptyText}>
                {hasCollected
                  ? 'Пока нечего предложить — мало истории покупок'
                  : 'Соберите корзину на неделю на основе своих покупок'}
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
          ) : null}
          {basketMessage && <Text style={styles.basketMessage}>{basketMessage}</Text>}
          <Text style={styles.appiLabel}>🍊 Спроси Аппи</Text>
          <View style={styles.basketInputRow}>
            <TextInput
              style={styles.basketInput}
              placeholder="Например: добавь молоко"
              placeholderTextColor={BrandColors.textSecondary}
              value={instructionText}
              onChangeText={setInstructionText}
              editable={!basketLoading}
              returnKeyType="send"
              onSubmitEditing={handleSendInstruction}
            />
            <TouchableOpacity
              style={styles.basketSendBtn}
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
                    trackColor={{ false: BrandColors.cardBorder, true: BrandColors.green }}
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

        {/* Tasks */}
        <Text style={styles.sectionTitle}>Задания</Text>
        <View style={styles.tasksList}>
          {challenges.map(challenge => (
            <TaskCard key={challenge.id} challenge={challenge} />
          ))}
        </View>

        {/* Leaderboard */}
        <Text style={styles.sectionTitle}>Рейтинг экономии</Text>
        <View style={styles.leaderboardCard}>
          {leaderboard.map((entry, idx) => (
            <LeaderboardRow key={entry.rank} entry={entry} isLast={idx === leaderboard.length - 1} />
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

function TaskCard({ challenge }: { challenge: ChallengeItem }) {
  const progressPct = Math.min(100, Math.round((challenge.quantity_current / challenge.quantity_target) * 100));
  const done = challenge.status === 'выполнено';

  return (
    <View style={styles.taskCard}>
      <View style={styles.taskTopRow}>
        <View style={styles.taskTextBlock}>
          <Text style={styles.taskTitle}>{challenge.title}</Text>
          <Text style={styles.taskSub}>{challenge.description}</Text>
        </View>
        {done ? (
          <View style={styles.doneCircle}>
            <Text style={styles.doneCheck}>✓</Text>
          </View>
        ) : (
          <View style={styles.progressPill}>
            <Text style={styles.progressPillText}>{challenge.quantity_current}/{challenge.quantity_target}</Text>
          </View>
        )}
      </View>

      {/* Task progress bar */}
      <View style={styles.taskProgressTrack}>
        <View
          style={[
            styles.taskProgressFill,
            {
              width: `${progressPct}%` as `${number}%`,
              backgroundColor: done ? BrandColors.green : BrandColors.red,
            },
          ]}
        />
      </View>

      {/* Reward */}
      <View style={[styles.rewardBlock, { backgroundColor: done ? BrandColors.greenLight : BrandColors.rewardOrangeBg }]}>
        <View style={[styles.rewardDot, { backgroundColor: done ? BrandColors.green : BrandColors.gold }]} />
        <Text style={styles.rewardText}>+{challenge.reward_rub} ₽ при выполнении</Text>
      </View>
    </View>
  );
}

function LeaderboardRow({ entry, isLast }: { entry: LeaderboardEntry; isLast: boolean }) {
  return (
    <View style={[styles.leaderboardRow, entry.me && styles.leaderboardRowMe, !isLast && styles.leaderboardRowBorder]}>
      <Text style={[styles.leaderboardRank, entry.rank === 1 && styles.leaderboardRankGold]}>
        {entry.rank}
      </Text>
      <View style={styles.leaderboardAvatar}>
        <Text style={styles.leaderboardAvatarText}>{entry.initial}</Text>
      </View>
      <Text style={[styles.leaderboardName, entry.me && styles.leaderboardNameMe]}>{entry.name}</Text>
      <Text style={styles.leaderboardSaved}>−{entry.saved} ₽</Text>
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
  headerRight: {
    flexDirection: 'row',
    gap: 4,
  },
  iconBtn: {
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
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    gap: 16,
  },
  card: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 16,
    gap: 12,
  },
  cardHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 8,
  },
  cardHeaderLabel: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  savedBadge: {
    backgroundColor: BrandColors.greenLight,
    borderRadius: 100,
    paddingVertical: 4,
    paddingHorizontal: 10,
  },
  savedBadgeText: {
    color: BrandColors.green,
    fontSize: 13,
    fontWeight: '700',
  },
  progressBarTrack: {
    height: 10,
    borderRadius: 100,
    backgroundColor: BrandColors.elementBg,
    overflow: 'hidden',
    flexDirection: 'row',
  },
  progressBarGreen: {
    height: 10,
    backgroundColor: BrandColors.green,
    borderRadius: 100,
  },
  progressBarGray: {
    height: 10,
    backgroundColor: '#D9D8D3',
    borderRadius: 100,
  },
  legendRow: {
    flexDirection: 'row',
    gap: 16,
    flexWrap: 'wrap',
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  legendDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  legendText: {
    fontSize: 12,
    color: BrandColors.textSecondary,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  tasksList: {
    gap: 12,
  },
  basketCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 14,
    gap: 10,
  },
  basketRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  basketItemInfo: {
    flex: 1,
  },
  basketItemName: {
    fontSize: 14,
    color: BrandColors.textPrimary,
  },
  basketItemQty: {
    fontSize: 13,
    color: BrandColors.textSecondary,
    fontWeight: '600',
  },
  basketItemPrices: {
    alignItems: 'flex-end',
  },
  basketItemBasePrice: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    textDecorationLine: 'line-through',
  },
  basketItemPaidPrice: {
    fontSize: 14,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  basketTotals: {
    borderTopWidth: 1,
    borderTopColor: BrandColors.cardBorder,
    paddingTop: 10,
    gap: 6,
  },
  basketTotalsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  basketTotalsLabel: {
    fontSize: 13,
    color: BrandColors.textSecondary,
  },
  basketTotalsValue: {
    fontSize: 15,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  basketTotalsValueGreen: {
    fontSize: 15,
    fontWeight: '700',
    color: BrandColors.green,
  },
  basketTotalsDiscount: {
    fontSize: 13,
    fontWeight: '600',
    color: BrandColors.green,
  },
  basketEmptyText: {
    fontSize: 13,
    color: BrandColors.textSecondary,
  },
  basketCollectBlock: {
    gap: 10,
    alignItems: 'flex-start',
  },
  collectBtn: {
    backgroundColor: BrandColors.dark,
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  collectBtnDisabled: {
    backgroundColor: BrandColors.cardBorder,
  },
  collectBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '700',
  },
  basketMessage: {
    fontSize: 12.5,
    color: BrandColors.textSecondary,
    fontStyle: 'italic',
  },
  appiLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: BrandColors.textSecondary,
  },
  basketInputRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  basketInput: {
    flex: 1,
    backgroundColor: BrandColors.elementBg,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
    color: BrandColors.textPrimary,
  },
  basketSendBtn: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: BrandColors.dark,
    alignItems: 'center',
    justifyContent: 'center',
  },
  basketSendBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  checkoutBtn: {
    backgroundColor: BrandColors.green,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkoutBtnDisabled: {
    backgroundColor: BrandColors.cardBorder,
  },
  checkoutBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
  taskCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 14,
    gap: 10,
  },
  taskTopRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 8,
  },
  taskTextBlock: {
    flex: 1,
    gap: 3,
  },
  taskTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  taskSub: {
    fontSize: 13,
    color: BrandColors.textSecondary,
  },
  doneCircle: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: BrandColors.green,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  doneCheck: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '700',
  },
  progressPill: {
    backgroundColor: BrandColors.elementBg,
    borderRadius: 100,
    paddingVertical: 3,
    paddingHorizontal: 10,
    marginTop: 2,
  },
  progressPillText: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    fontWeight: '600',
  },
  taskProgressTrack: {
    height: 7,
    backgroundColor: BrandColors.elementBg,
    borderRadius: 100,
    overflow: 'hidden',
  },
  taskProgressFill: {
    height: 7,
    borderRadius: 100,
  },
  rewardBlock: {
    borderRadius: 10,
    padding: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  rewardDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    flexShrink: 0,
  },
  rewardText: {
    fontSize: 12.5,
    color: BrandColors.textPrimary,
    flex: 1,
  },
  leaderboardCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 8,
    overflow: 'hidden',
  },
  leaderboardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 10,
    borderRadius: 12,
  },
  leaderboardRowMe: {
    backgroundColor: BrandColors.rewardOrangeBg,
  },
  leaderboardRowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.04)',
  },
  leaderboardRank: {
    width: 20,
    fontSize: 14,
    fontWeight: '700',
    color: BrandColors.textSecondary,
    textAlign: 'center',
  },
  leaderboardRankGold: {
    color: BrandColors.gold,
  },
  leaderboardAvatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: BrandColors.elementBg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  leaderboardAvatarText: {
    fontSize: 13,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  leaderboardName: {
    flex: 1,
    fontSize: 14,
    color: BrandColors.textPrimary,
  },
  leaderboardNameMe: {
    fontWeight: '700',
  },
  leaderboardSaved: {
    fontSize: 14,
    fontWeight: '600',
    color: BrandColors.green,
  },
});
