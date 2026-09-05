import { useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import { apiLogin, apiRegister } from '@/api/client';
import { CustomTabBar, TabScreen } from '@/components/custom-tab-bar';
import { ChallengesView } from '@/components/screens/challenges-view';
import { HistoryView } from '@/components/screens/history-view';
import { HomeView } from '@/components/screens/home-view';
import { PointsView } from '@/components/screens/points-view';
import { ReceiptDetailView } from '@/components/screens/receipt-detail-view';
import { SavingsView } from '@/components/screens/savings-view';
import { BrandColors } from '@/constants/theme';
import { useEconomy } from '@/hooks/useEconomy';
import { useMockData } from '@/mock-data';

type Screen = 'home' | 'savings' | 'history' | 'catalog' | 'cart' | 'appi' | 'profile' | 'challenges' | 'receipt-detail' | 'points';

function LoginScreen({ onLogin }: { onLogin: (token: string) => void }) {
  const insets = useSafeAreaInsets();
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    const trimmed = phone.trim();
    if (!trimmed) {
      Alert.alert('Ошибка', 'Введите номер телефона');
      return;
    }
    setLoading(true);
    try {
      const token = await apiLogin(trimmed);
      onLogin(token);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Ошибка входа';
      Alert.alert('Ошибка', msg);
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister() {
    const trimmed = phone.trim();
    if (!trimmed) {
      Alert.alert('Ошибка', 'Введите номер телефона');
      return;
    }
    setLoading(true);
    try {
      const token = await apiRegister(trimmed);
      onLogin(token);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Ошибка регистрации';
      Alert.alert('Ошибка', msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={[styles.loginRoot, { paddingTop: insets.top + 60 }]}>
      <Text style={styles.loginTitle}>Добро пожаловать</Text>
      <Text style={styles.loginSubtitle}>Введите номер телефона, чтобы войти или зарегистрироваться</Text>
      <TextInput
        style={styles.input}
        placeholder="+7 000 000-00-00"
        placeholderTextColor={BrandColors.textSecondary}
        value={phone}
        onChangeText={setPhone}
        keyboardType="phone-pad"
        autoComplete="tel"
        textContentType="telephoneNumber"
      />
      <TouchableOpacity style={styles.loginBtn} onPress={handleLogin} activeOpacity={0.8} disabled={loading}>
        {loading
          ? <ActivityIndicator color="#fff" />
          : <Text style={styles.loginBtnText}>Войти</Text>
        }
      </TouchableOpacity>
      <TouchableOpacity style={styles.registerBtn} onPress={handleRegister} activeOpacity={0.8} disabled={loading}>
        <Text style={styles.registerBtnText}>Зарегистрироваться</Text>
      </TouchableOpacity>
    </View>
  );
}

function AppContent({ token }: { token: string }) {
  const [screen, setScreen] = useState<Screen>('home');
  const [prevScreen, setPrevScreen] = useState<Screen>('home');
  const [selectedReceiptId, setSelectedReceiptId] = useState<string | null>(null);
  const [autoCollectBasket, setAutoCollectBasket] = useState(false);
  const data = useMockData();
  const { economy, refetch: refetchEconomy } = useEconomy(token);

  const totalSaved = economy?.total_saved ?? 0;
  const totalPaid = economy?.total_paid ?? 0;

  function navigate(next: Screen) {
    setPrevScreen(screen);
    setScreen(next);
  }

  function goBack() {
    setScreen(prevScreen === screen ? 'home' : prevScreen);
  }

  function openReceipt(id: string) {
    setSelectedReceiptId(id);
    navigate('receipt-detail');
  }

  return (
    <View style={styles.root}>
      <View style={styles.content}>
        {screen === 'home' && (
          <HomeView
            token={token}
            onHistory={() => navigate('history')}
            onChallenges={() => navigate('challenges')}
            onPoints={() => navigate('points')}
            onOpenBasket={() => {
              setAutoCollectBasket(true);
              navigate('savings');
            }}
          />
        )}
        {screen === 'points' && (
          <PointsView token={token} goBack={goBack} />
        )}
        {screen === 'savings' && (
          <SavingsView
            leaderboard={data.leaderboard}
            savings={{ paid: totalPaid, withoutDiscount: totalPaid + totalSaved }}
            token={token}
            goHome={() => navigate('home')}
            goHistory={() => navigate('history')}
            goChallenges={() => navigate('challenges')}
            onOrderPlaced={refetchEconomy}
            autoCollect={autoCollectBasket}
            onAutoCollectHandled={() => setAutoCollectBasket(false)}
          />
        )}
        {screen === 'history' && (
          <HistoryView
            token={token}
            totalSaved={totalSaved}
            totalPaid={totalPaid}
            goBack={goBack}
            onReceiptPress={openReceipt}
          />
        )}
        {screen === 'challenges' && (
          <ChallengesView token={token} goBack={goBack} />
        )}
        {screen === 'receipt-detail' && selectedReceiptId && (
          <ReceiptDetailView token={token} receiptId={selectedReceiptId} goBack={goBack} />
        )}
      </View>
      <CustomTabBar
        activeScreen={(screen === 'savings' ? 'cart' : screen) as TabScreen}
        onTabPress={(tab) => navigate(tab === 'cart' ? 'savings' : tab)}
      />
    </View>
  );
}

export default function IndexScreen() {
  const [token, setToken] = useState<string | null>(null);

  return (
    <SafeAreaProvider>
      {token
        ? <AppContent key={token} token={token} />
        : <LoginScreen onLogin={setToken} />
      }
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: BrandColors.appBg,
  },
  content: {
    flex: 1,
  },
  loginRoot: {
    flex: 1,
    backgroundColor: BrandColors.appBg,
    paddingHorizontal: 24,
    gap: 14,
  },
  loginTitle: {
    fontSize: 26,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  loginSubtitle: {
    fontSize: 14,
    color: BrandColors.textSecondary,
    lineHeight: 20,
    marginBottom: 4,
  },
  input: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 17,
    color: BrandColors.textPrimary,
  },
  loginBtn: {
    backgroundColor: BrandColors.dark,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 4,
  },
  loginBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  registerBtn: {
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: BrandColors.cardBorder,
    paddingVertical: 15,
    alignItems: 'center',
  },
  registerBtnText: {
    color: BrandColors.textPrimary,
    fontSize: 16,
    fontWeight: '600',
  },
});
