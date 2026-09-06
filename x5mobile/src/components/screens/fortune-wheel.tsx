import { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';

import type { FortunePrize } from '@/hooks/useFortuneWheel';

export interface SpinRequest {
  targetIndex: number;
  nonce: number;
}

interface FortuneWheelProps {
  prizes: FortunePrize[];
  size: number;
  spinRequest: SpinRequest | null;
  onSpinComplete: () => void;
}

export function FortuneWheel({ prizes, size, spinRequest, onSpinComplete }: FortuneWheelProps) {
  const rotation = useSharedValue(0);
  const count = Math.max(prizes.length, 1);
  const angle = 360 / count;
  const radius = size / 2;
  const sliceHeight = radius + 8;
  const halfBase = sliceHeight * Math.tan((angle / 2) * Math.PI / 180);

  useEffect(() => {
    if (!spinRequest) return;
    const extraTurns = 6;
    const current = rotation.value;
    const targetMod = (((-spinRequest.targetIndex * angle) % 360) + 360) % 360;
    const currentMod = ((current % 360) + 360) % 360;
    let delta = targetMod - currentMod;
    if (delta <= 0) delta += 360;
    const next = current + extraTurns * 360 + delta;

    rotation.value = withTiming(
      next,
      { duration: 4600, easing: Easing.bezier(0.1, 0.72, 0.12, 1) },
      (finished) => {
        'worklet';
        if (finished) scheduleOnRN(onSpinComplete);
      },
    );
  }, [spinRequest?.nonce]);

  const wheelStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${rotation.value}deg` }],
  }));

  return (
    <View style={[styles.stage, { width: size + 40, height: size + 40 }]}>
      <View style={styles.leaf} />
      <View style={styles.stem} />
      <View style={[styles.rind, { width: size + 22, height: size + 22, borderRadius: (size + 22) / 2 }]}>
        <View style={[styles.pith, { width: size + 8, height: size + 8, borderRadius: (size + 8) / 2 }]}>
          <View style={[styles.clip, { width: size, height: size, borderRadius: radius }]}>
            <Animated.View style={[{ width: size, height: size }, wheelStyle]}>
              {prizes.map((prize, index) => (
                <View
                  key={prize.id}
                  style={[
                    styles.segment,
                    {
                      left: radius - halfBase,
                      top: radius - sliceHeight,
                      borderLeftWidth: halfBase,
                      borderRightWidth: halfBase,
                      borderTopWidth: sliceHeight,
                      borderTopColor: prize.color,
                      transform: [{ rotate: `${index * angle}deg` }],
                      transformOrigin: 'center bottom',
                    },
                  ]}
                />
              ))}
              {prizes.map((_, index) => (
                <View
                  key={`pith-${index}`}
                  pointerEvents="none"
                  style={[
                    styles.divider,
                    {
                      left: radius - 2,
                      top: 0,
                      height: radius,
                      transform: [{ rotate: `${index * angle + angle / 2}deg` }],
                      transformOrigin: 'center bottom',
                    },
                  ]}
                />
              ))}
              {prizes.map((prize, index) => {
                const deg = index * angle;
                const rad = ((deg - 90) * Math.PI) / 180;
                const r = radius * 0.58;
                const x = radius + r * Math.cos(rad);
                const y = radius + r * Math.sin(rad);
                return (
                  <View
                    key={`label-${prize.id}`}
                    pointerEvents="none"
                    style={[
                      styles.label,
                      {
                        left: x - 34,
                        top: y - 22,
                        transform: [{ rotate: `${deg}deg` }],
                      },
                    ]}>
                    <Text style={styles.labelEmoji}>{prize.emoji}</Text>
                    <Text style={[styles.labelText, { color: prize.textColor }]}>{prize.shortLabel}</Text>
                  </View>
                );
              })}
            </Animated.View>
          </View>
        </View>
      </View>

      <View style={styles.pointerWrap} pointerEvents="none">
        <View style={styles.pointerStem} />
        <View style={styles.pointer} />
      </View>

      <View style={styles.hub} pointerEvents="none">
        <Text style={styles.hubEmoji}>🍊</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  leaf: {
    position: 'absolute',
    top: 2,
    right: 18,
    width: 22,
    height: 12,
    borderRadius: 10,
    backgroundColor: '#3B9A3B',
    transform: [{ rotate: '28deg' }],
    zIndex: 5,
  },
  stem: {
    position: 'absolute',
    top: 8,
    width: 8,
    height: 14,
    borderRadius: 4,
    backgroundColor: '#6B3F16',
    zIndex: 5,
  },
  rind: {
    backgroundColor: '#E86A00',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#8A3A00',
    shadowOpacity: 0.28,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
  },
  pith: {
    backgroundColor: '#FFF3D6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  clip: {
    overflow: 'hidden',
    backgroundColor: '#FFB347',
  },
  segment: {
    position: 'absolute',
    top: 0,
    width: 0,
    height: 0,
    borderLeftColor: 'rgba(0,0,0,0)',
    borderRightColor: 'rgba(0,0,0,0)',
  },
  divider: {
    position: 'absolute',
    width: 4,
    backgroundColor: '#FFF6E4',
  },
  label: {
    position: 'absolute',
    width: 68,
    alignItems: 'center',
  },
  labelEmoji: {
    fontSize: 16,
    lineHeight: 18,
  },
  labelText: {
    fontSize: 11,
    fontWeight: '800',
    marginTop: 1,
  },
  pointerWrap: {
    position: 'absolute',
    top: 6,
    alignItems: 'center',
    zIndex: 6,
  },
  pointerStem: {
    width: 8,
    height: 10,
    backgroundColor: '#164E2B',
    borderTopLeftRadius: 3,
    borderTopRightRadius: 3,
  },
  pointer: {
    width: 0,
    height: 0,
    borderLeftWidth: 12,
    borderRightWidth: 12,
    borderTopWidth: 18,
    borderLeftColor: 'rgba(0,0,0,0)',
    borderRightColor: 'rgba(0,0,0,0)',
    borderTopColor: '#164E2B',
  },
  hub: {
    position: 'absolute',
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: '#FFF8E7',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 4,
    borderColor: '#E86A00',
    zIndex: 3,
    shadowColor: '#000',
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
  },
  hubEmoji: {
    fontSize: 26,
  },
});
