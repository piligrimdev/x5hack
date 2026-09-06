import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { CustomTabBar, TabScreen } from '@/components/custom-tab-bar';
import { AppiView } from '@/components/screens/appi-view';
import { ChallengesView } from '@/components/screens/challenges-view';
import { FortuneWheelView } from '@/components/screens/fortune-wheel-view';
import { HistoryView } from '@/components/screens/history-view';
import { HomeView } from '@/components/screens/home-view';
import { LoginView } from '@/components/screens/login-view';
import { PointsView } from '@/components/screens/points-view';
import { ReceiptDetailView } from '@/components/screens/receipt-detail-view';
import { DiscountsView } from '@/components/screens/discounts-view';
import { ReferralView } from '@/components/screens/referral-view';
import { SavingsLeaderboardView } from '@/components/screens/savings-leaderboard-view';
import { SavingsView } from '@/components/screens/savings-view';
import { BrandColors } from '@/constants/theme';
import { useBasket } from '@/hooks/useBasket';
import { useEconomy } from '@/hooks/useEconomy';

type Screen = 'home' | 'history' | 'catalog' | 'cart' | 'appi' | 'profile' | 'challenges' | 'receipt-detail' | 'points' | 'wheel' | 'leaderboard' | 'referral' | 'discounts';

function AppContent({ token }: { token: string }) {
  const [screen, setScreen] = useState<Screen>('home');
  const [prevScreen, setPrevScreen] = useState<Screen>('home');
  const [selectedReceiptId, setSelectedReceiptId] = useState<string | null>(null);
  const basket = useBasket(token);
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
            onPoints={() => navigate('points')}
            onOpenAppi={() => navigate('appi')}
            onHistory={() => navigate('history')}
            onInvite={() => navigate('referral')}
            onDiscounts={() => navigate('discounts')}
          />
        )}
        {(screen === 'appi' || screen === 'leaderboard') && (
          <View
            style={screen === 'appi' ? styles.screenFill : styles.screenHidden}
            pointerEvents={screen === 'appi' ? 'auto' : 'none'}>
            <AppiView
              token={token}
              basket={basket}
              onOpenBasket={() => navigate('cart')}
              onChallenges={() => navigate('challenges')}
              onOpenWheel={() => navigate('wheel')}
              onOpenLeaderboard={() => navigate('leaderboard')}
            />
          </View>
        )}
        {screen === 'leaderboard' && (
          <View style={styles.screenFill}>
            <SavingsLeaderboardView token={token} goBack={goBack} />
          </View>
        )}
        {screen === 'points' && (
          <PointsView token={token} goBack={goBack} />
        )}
        {screen === 'cart' && (
          <SavingsView
            onOrderPlaced={refetchEconomy}
            basket={basket}
            token={token}
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
        {screen === 'wheel' && (
          <FortuneWheelView token={token} goBack={goBack} />
        )}
        {screen === 'referral' && (
          <ReferralView
            token={token}
            goBack={goBack}
            onOpenDiscounts={() => navigate('discounts')}
          />
        )}
        {screen === 'discounts' && (
          <DiscountsView token={token} goBack={goBack} />
        )}
        {screen === 'receipt-detail' && selectedReceiptId && (
          <ReceiptDetailView token={token} receiptId={selectedReceiptId} goBack={goBack} />
        )}
      </View>
      <CustomTabBar
        activeScreen={(
          screen === 'challenges' || screen === 'wheel' || screen === 'leaderboard'
            ? 'appi'
            : screen === 'catalog' || screen === 'profile' || screen === 'appi' || screen === 'cart'
              ? screen
              : 'home'
        ) as TabScreen}
        onTabPress={navigate}
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
        : <LoginView onLogin={setToken} />
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
  screenFill: {
    flex: 1,
  },
  screenHidden: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
    overflow: 'hidden',
  },
});
