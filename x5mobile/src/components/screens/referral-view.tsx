import * as Clipboard from 'expo-clipboard';
import { useEffect, useRef } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { ReferralOut, ReferralStatus } from '@/api/client';
import { INVITER_STEPS } from '@/constants/referral';
import { useReferrals } from '@/hooks/useReferrals';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

const STATUS_LABEL: Record<ReferralStatus, string> = {
  issued: 'Ожидает друга',
  awaiting_purchase: 'Друг активировал, ждём покупку',
  rewarded: 'Награда начислена',
  expired: 'Окно покупки истекло',
};

interface ReferralViewProps {
  token: string;
  goBack: () => void;
  onOpenDiscounts?: () => void;
}

export function ReferralView({ token, goBack, onOpenDiscounts }: ReferralViewProps) {
  const insets = useSafeAreaInsets();
  const { items, latest, loading, issuing, error, issue } = useReferrals(token);
  const autoIssued = useRef(false);

  useEffect(() => {
    if (!loading && items.length === 0 && !issuing && !autoIssued.current) {
      autoIssued.current = true;
      void issue();
    }
  }, [loading, items.length, issuing, issue]);

  async function copyCode(code: string) {
    await Clipboard.setStringAsync(code);
  }

  async function shareCode(code: string) {
    await Share.share({
      message: `Присоединяйся к программе лояльности. Мой код: ${code}`,
    });
  }

  return (
    <View style={[styles.root, { paddingTop: insets.top + 8 }]}>
      <TouchableOpacity onPress={goBack} style={styles.back} activeOpacity={0.7}>
        <Text style={styles.backText}>← Назад</Text>
      </TouchableOpacity>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Пригласить друга</Text>
        <Text style={styles.subtitle}>
          Код даёт другу скидку, а вам — купоны и кешбек после его покупки
        </Text>

        <View style={styles.howTo}>
          <Text style={styles.howToTitle}>Как получить бонусы</Text>
          {INVITER_STEPS.map((step, index) => (
            <View key={step} style={styles.howToRow}>
              <Text style={styles.howToIndex}>{index + 1}</Text>
              <Text style={styles.howToText}>{step}</Text>
            </View>
          ))}
        </View>

        {onOpenDiscounts ? (
          <TouchableOpacity style={styles.discountsBtn} onPress={onOpenDiscounts} activeOpacity={0.8}>
            <Text style={styles.discountsBtnText}>Мои скидки и акции</Text>
            <Text style={styles.discountsBtnHint}>Что уже действует на ваши покупки</Text>
          </TouchableOpacity>
        ) : null}

        {loading && !latest ? (
          <ActivityIndicator color={GREEN} style={styles.spinner} />
        ) : null}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {latest ? (
          <View style={styles.card}>
            <Text style={styles.codeLabel}>Ваш код</Text>
            <Text style={styles.code}>{latest.code}</Text>
            <Text style={styles.status}>{STATUS_LABEL[latest.status]}</Text>
            <View style={styles.actions}>
              <TouchableOpacity
                style={styles.primaryBtn}
                onPress={() => copyCode(latest.code)}
                activeOpacity={0.8}>
                <Text style={styles.primaryBtnText}>Скопировать</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.secondaryBtn}
                onPress={() => shareCode(latest.code)}
                activeOpacity={0.8}>
                <Text style={styles.secondaryBtnText}>Отправить</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : null}

        <TouchableOpacity
          style={[styles.issueBtn, issuing && styles.btnDisabled]}
          onPress={() => void issue()}
          disabled={issuing}
          activeOpacity={0.8}>
          <Text style={styles.issueBtnText}>
            {items.length === 0 ? 'Создать код' : 'Создать ещё один код'}
          </Text>
        </TouchableOpacity>

        <View style={styles.list}>
          {items.map((item: ReferralOut) => (
            <View key={item.id} style={styles.row}>
              <Text style={styles.rowCode}>{item.code}</Text>
              <Text style={styles.rowStatus}>{STATUS_LABEL[item.status]}</Text>
            </View>
          ))}
        </View>
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
  scroll: {
    paddingBottom: 40,
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
  howTo: {
    backgroundColor: '#fff',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 16,
    gap: 12,
    marginBottom: 12,
  },
  howToTitle: {
    color: DARK_GREEN,
    fontSize: 16,
    fontWeight: '800',
  },
  howToRow: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'flex-start',
  },
  howToIndex: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: '#E8F6EC',
    color: GREEN,
    fontSize: 13,
    fontWeight: '800',
    textAlign: 'center',
    lineHeight: 22,
    overflow: 'hidden',
  },
  howToText: {
    flex: 1,
    color: TEXT,
    fontSize: 14,
    lineHeight: 20,
  },
  discountsBtn: {
    backgroundColor: '#fff',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: GREEN,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 16,
  },
  discountsBtnText: {
    color: DARK_GREEN,
    fontSize: 16,
    fontWeight: '800',
  },
  discountsBtnHint: {
    color: MUTED,
    fontSize: 13,
    marginTop: 4,
  },
  spinner: {
    marginVertical: 24,
  },
  error: {
    color: '#C0392B',
    marginBottom: 12,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 20,
    alignItems: 'center',
  },
  codeLabel: {
    color: MUTED,
    fontSize: 13,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  code: {
    color: TEXT,
    fontSize: 32,
    fontWeight: '800',
    letterSpacing: 3,
    marginTop: 8,
  },
  status: {
    color: GREEN,
    marginTop: 8,
    fontWeight: '600',
  },
  actions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 16,
  },
  primaryBtn: {
    backgroundColor: GREEN,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  primaryBtnText: {
    color: '#fff',
    fontWeight: '700',
  },
  secondaryBtn: {
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: GREEN,
  },
  secondaryBtnText: {
    color: GREEN,
    fontWeight: '700',
  },
  issueBtn: {
    marginTop: 16,
    alignSelf: 'flex-start',
  },
  issueBtnText: {
    color: DARK_GREEN,
    fontWeight: '700',
    fontSize: 16,
  },
  btnDisabled: {
    opacity: 0.5,
  },
  list: {
    paddingTop: 20,
    paddingBottom: 40,
    gap: 10,
  },
  row: {
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  rowCode: {
    color: TEXT,
    fontWeight: '700',
    letterSpacing: 1,
  },
  rowStatus: {
    color: MUTED,
    flexShrink: 1,
    textAlign: 'right',
  },
});
