import { type ReactNode } from 'react';
import { Platform, StyleSheet, useWindowDimensions, View } from 'react-native';

import { isPhoneWebLayout } from '@/constants/web-layout';

const DESKTOP_MIN_WIDTH = 560;
const PHONE_W = 390;
const PHONE_H = 844;
const BEZEL = 10;
const OUTER_W = PHONE_W + BEZEL * 2;
const OUTER_H = PHONE_H + BEZEL * 2;
const STAGE_PAD = 32;

/** On a laptop/projector, show a full 390×844 phone and scale it to fit. */
export function WebPhoneShell({ children }: { children: ReactNode }) {
  const { width, height } = useWindowDimensions();
  const framed = Platform.OS === 'web' && isPhoneWebLayout() && width >= DESKTOP_MIN_WIDTH;

  if (!framed) {
    return <>{children}</>;
  }

  const scale = Math.min(
    Math.max(width - STAGE_PAD, 1) / OUTER_W,
    Math.max(height - STAGE_PAD, 1) / OUTER_H,
    1,
  );

  return (
    <View style={styles.stage}>
      <View style={{ width: OUTER_W * scale, height: OUTER_H * scale }}>
        <View style={[styles.scaler, { transform: [{ scale }] }]}>
          <View style={styles.bezel}>
            <View style={styles.screen}>{children}</View>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#141416',
    overflow: 'hidden',
  },
  scaler: {
    width: OUTER_W,
    height: OUTER_H,
    transformOrigin: 'top left',
  },
  bezel: {
    width: OUTER_W,
    height: OUTER_H,
    padding: BEZEL,
    borderRadius: 36,
    backgroundColor: '#1A1A1C',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
  },
  screen: {
    flex: 1,
    width: PHONE_W,
    height: PHONE_H,
    borderRadius: 22,
    overflow: 'hidden',
    backgroundColor: '#F6F4F1',
  },
});
