import { SymbolView } from 'expo-symbols';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export type TabScreen = 'home' | 'catalog' | 'cart' | 'appi' | 'profile';

interface CustomTabBarProps {
  activeScreen: TabScreen;
  onTabPress: (tab: TabScreen) => void;
}

const ACTIVE = '#292929';
const INACTIVE = '#9A9D9A';
const APPI_ORANGE = '#F56A00';

function HomeIcon({ color }: { color: string }) {
  return (
    <SymbolView
      name={{ ios: 'house.fill', android: 'home', web: 'home' }}
      tintColor={color}
      size={24}
      weight="semibold"
    />
  );
}

function CatalogIcon({ color }: { color: string }) {
  return (
    <SymbolView
      name={{ ios: 'minus.circle.fill', android: 'do_not_disturb_on', web: 'do_not_disturb_on' }}
      tintColor={color}
      size={24}
      weight="semibold"
    />
  );
}

function CartIcon({ color }: { color: string }) {
  return (
    <SymbolView
      name={{ ios: 'cart.fill', android: 'shopping_cart', web: 'shopping_cart' }}
      tintColor={color}
      size={24}
      weight="semibold"
    />
  );
}

function AppiIcon({ active }: { color: string; active?: boolean }) {
  return (
    <View style={[iconStyles.appi, !active && iconStyles.appiInactive]}>
      <Text style={iconStyles.appiEmoji}>🍊</Text>
      <View style={iconStyles.appiLeaf} />
    </View>
  );
}

function ProfileIcon({ color }: { color: string }) {
  return (
    <SymbolView
      name={{ ios: 'person.fill', android: 'person', web: 'person' }}
      tintColor={color}
      size={24}
      weight="semibold"
    />
  );
}

const iconStyles = StyleSheet.create({
  appi: {
    width: 29,
    height: 25,
    alignItems: 'center',
    justifyContent: 'center',
  },
  appiInactive: { opacity: 0.72 },
  appiEmoji: { fontSize: 25, lineHeight: 27 },
  appiLeaf: {
    position: 'absolute',
    right: 0,
    top: 0,
    width: 7,
    height: 4,
    borderRadius: 4,
    backgroundColor: '#3B9A3B',
    transform: [{ rotate: '-25deg' }],
  },
});

export function CustomTabBar({ activeScreen, onTabPress }: CustomTabBarProps) {
  const insets = useSafeAreaInsets();
  const tabs: {
    key: TabScreen;
    label: string;
    Icon: React.ComponentType<{ color: string; active?: boolean }>;
  }[] = [
    { key: 'home', label: 'Главная', Icon: HomeIcon },
    { key: 'catalog', label: 'Каталог', Icon: CatalogIcon },
    { key: 'cart', label: 'Корзина', Icon: CartIcon },
    { key: 'appi', label: 'Аппи', Icon: AppiIcon },
    { key: 'profile', label: 'Профиль', Icon: ProfileIcon },
  ];

  return (
    <View style={[styles.container, { paddingBottom: Math.max(insets.bottom, 7) }]}>
      {tabs.map(tab => {
        const active = tab.key === activeScreen;
        const color = tab.key === 'appi' && active ? APPI_ORANGE : active ? ACTIVE : INACTIVE;
        return (
          <TouchableOpacity
            key={tab.key}
            style={styles.tab}
            onPress={() => onTabPress(tab.key)}
            activeOpacity={0.68}>
            <tab.Icon color={color} active={active} />
            <Text style={[styles.label, { color }]}>{tab.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    minHeight: 69,
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#FFFFFF',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#E3E4E3',
    paddingTop: 9,
    paddingHorizontal: 13,
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'flex-start',
    gap: 4,
  },
  label: { fontSize: 10.5, fontWeight: '600' },
});
