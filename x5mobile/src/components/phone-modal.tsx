import { type ReactNode } from 'react';
import { Modal, Platform, StyleSheet, View } from 'react-native';

type PhoneModalProps = {
  visible: boolean;
  transparent?: boolean;
  animationType?: 'none' | 'slide' | 'fade';
  onRequestClose: () => void;
  children: ReactNode;
};

/**
 * RN Modal portals to document.body on web, so it ignores the phone frame.
 * Keep the sheet inside the 390×844 screen instead.
 */
export function PhoneModal({
  visible,
  transparent = true,
  animationType = 'fade',
  onRequestClose,
  children,
}: PhoneModalProps) {
  if (Platform.OS === 'web') {
    if (!visible) return null;
    return (
      <View style={styles.webHost} pointerEvents="box-none">
        {children}
      </View>
    );
  }

  return (
    <Modal
      visible={visible}
      transparent={transparent}
      animationType={animationType}
      onRequestClose={onRequestClose}>
      {children}
    </Modal>
  );
}

const styles = StyleSheet.create({
  webHost: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 40,
  },
});
