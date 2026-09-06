import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BasketItem, BasketState } from '@/hooks/useBasket';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

interface SavingsViewProps {
  onOrderPlaced: () => void;
  basket: BasketState;
}

export function SavingsView({ onOrderPlaced, basket }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
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
    if (await checkout()) onOrderPlaced();
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
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 18, paddingBottom: 28, gap: 12 },
  pageEyebrow: { color: DARK_GREEN, fontSize: 22, fontWeight: '900' },
  pageDescription: { color: MUTED, fontSize: 13, lineHeight: 18, marginBottom: 4 },
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
});
