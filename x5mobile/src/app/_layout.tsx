import { DarkTheme, DefaultTheme, ThemeProvider } from 'expo-router';
import { Slot } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StyleSheet, useColorScheme, View } from 'react-native';

import { AnimatedSplashOverlay } from '@/components/animated-icon';
import { WebPhoneShell } from '@/components/web-phone-shell';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <WebPhoneShell>
        <View style={styles.fill}>
          <AnimatedSplashOverlay />
          <Slot />
        </View>
      </WebPhoneShell>
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
    height: '100%',
    overflow: 'hidden',
  },
});

