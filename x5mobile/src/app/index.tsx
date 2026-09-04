import { useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { CustomTabBar } from '@/components/custom-tab-bar';
import { HistoryView } from '@/components/screens/history-view';
import { HomeView } from '@/components/screens/home-view';
import { SavingsView } from '@/components/screens/savings-view';
import { BrandColors } from '@/constants/theme';
import { useMockData } from '@/mock-data';

type Screen = 'home' | 'savings' | 'history';

export default function IndexScreen() {
  const [screen, setScreen] = useState<Screen>('home');
  const [prevScreen, setPrevScreen] = useState<Screen>('home');
  const data = useMockData();

  function navigate(next: Screen) {
    setPrevScreen(screen);
    setScreen(next);
  }

  function goBack() {
    setScreen(prevScreen === screen ? 'home' : prevScreen);
  }

  return (
    <SafeAreaProvider>
      <View style={styles.root}>
        <View style={styles.content}>
          {screen === 'home' && (
            <HomeView
              user={data.user}
              goSavings={() => navigate('savings')}
              goHistory={() => navigate('history')}
            />
          )}
          {screen === 'savings' && (
            <SavingsView
              tasks={data.tasks}
              leaderboard={data.leaderboard}
              savings={data.savings}
              goHome={() => navigate('home')}
              goHistory={() => navigate('history')}
            />
          )}
          {screen === 'history' && (
            <HistoryView
              history={data.history}
              savings={data.savings}
              goBack={goBack}
            />
          )}
        </View>
        <CustomTabBar
          activeScreen={screen}
          onTabPress={(tab) => {
            if (tab === 'home') navigate('home');
          }}
        />
      </View>
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
});
