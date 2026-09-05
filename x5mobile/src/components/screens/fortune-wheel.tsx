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
  const count = prizes.length;
  const angle = 360 / count;
  const radius = size / 2;
  const sliceHeight = radius + 6;
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
    <View style={[styles.stage, { width: size + 36, height: size + 36 }]}>
      <View style={[styles.rim, { width: size + 20, height: size + 20, borderRadius: (size + 20) / 2 }]}>
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
                      left: x - 32,
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
  rim: {
    backgroundColor: '#E8C77A',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#8A5A12',
    shadowOpacity: 0.28,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
    borderWidth: 3,
    borderColor: '#C99A3E',
  },
  clip: {
    overflow: 'hidden',
    backgroundColor: '#1B5E35',
  },
  segment: {
    position: 'absolute',
    top: 0,
    width: 0,
    height: 0,
    borderLeftColor: 'rgba(0,0,0,0)',
    borderRightColor: 'rgba(0,0,0,0)',
  },
  label: {
    position: 'absolute',
    width: 64,
    alignItems: 'center',
  },
  labelEmoji: {
    fontSize: 16,
    lineHeight: 18,
  },
  labelText: {
    fontSize: 10,
    fontWeight: '800',
    marginTop: 1,
  },
  pointerWrap: {
    position: 'absolute',
    top: 0,
    alignItems: 'center',
    zIndex: 4,
  },
  pointerStem: {
    width: 8,
    height: 10,
    backgroundColor: '#FF6D00',
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
    borderTopColor: '#FF6D00',
  },
  hub: {
    position: 'absolute',
    width: 58,
    height: 58,
    borderRadius: 29,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 4,
    borderColor: '#FF6D00',
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
