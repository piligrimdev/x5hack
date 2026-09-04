import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export type TabScreen = 'home' | 'catalog' | 'cart' | 'appi' | 'profile';

interface CustomTabBarProps {
  activeScreen: TabScreen;
  onTabPress: (tab: TabScreen) => void;
}

const GREEN_ACTIVE = '#25A244';
const INACTIVE = '#B4B3AF';

function HomeIcon({ color }: { color: string }) {
  // 4-leaf clover
  return (
    <View style={iconS.clover}>
      <View style={iconS.cloverRow}>
        <View style={[iconS.cloverLeaf, { backgroundColor: color }]} />
        <View style={[iconS.cloverLeaf, { backgroundColor: color }]} />
      </View>
      <View style={iconS.cloverRow}>
        <View style={[iconS.cloverLeaf, { backgroundColor: color }]} />
        <View style={[iconS.cloverLeaf, { backgroundColor: color }]} />
      </View>
    </View>
  );
}

function CatalogIcon({ color }: { color: string }) {
  return (
    <View style={iconS.catalog}>
      <View style={[iconS.searchCircle, { borderColor: color }]}>
        <View style={[iconS.searchLines, { gap: 2 }]}>
          <View style={[iconS.line, { backgroundColor: color }]} />
          <View style={[iconS.line, { backgroundColor: color, width: 10 }]} />
        </View>
      </View>
    </View>
  );
}

function CartIcon({ color }: { color: string }) {
  return (
    <View style={iconS.cart}>
      <View style={[iconS.cartBasket, { borderColor: color }]}>
        <View style={iconS.cartHandleRow}>
          <View style={[iconS.cartHandle, { borderColor: color }]} />
        </View>
      </View>
    </View>
  );
}

function AppiIcon({ color }: { color: string }) {
  const isActive = color === GREEN_ACTIVE;
  return (
    <View style={[iconS.appiCircle, { backgroundColor: isActive ? '#FF6D00' : '#E0E0E0' }]}>
      <Text style={iconS.appiEmoji}>🙂</Text>
    </View>
  );
}

function ProfileIcon({ color }: { color: string }) {
  return (
    <View style={iconS.profile}>
      <View style={[iconS.profileHead, { backgroundColor: color }]} />
      <View style={[iconS.profileBody, { borderColor: color }]} />
    </View>
  );
}

const iconS = StyleSheet.create({
  clover: {
    width: 22,
    height: 22,
    gap: 2,
  },
  cloverRow: {
    flex: 1,
    flexDirection: 'row',
    gap: 2,
  },
  cloverLeaf: {
    flex: 1,
    borderRadius: 6,
  },
  catalog: {
    width: 22,
    height: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchCircle: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchLines: {
    width: 12,
  },
  line: {
    height: 2,
    width: 12,
    borderRadius: 1,
  },
  cart: {
    width: 24,
    height: 22,
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  cartBasket: {
    width: 22,
    height: 14,
    borderRadius: 4,
    borderWidth: 2,
    borderTopWidth: 0,
    alignItems: 'center',
    justifyContent: 'flex-start',
    paddingTop: 0,
    position: 'relative',
  },
  cartHandleRow: {
    position: 'absolute',
    top: -10,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  cartHandle: {
    width: 14,
    height: 10,
    borderTopLeftRadius: 7,
    borderTopRightRadius: 7,
    borderWidth: 2,
    borderBottomWidth: 0,
  },
  appiCircle: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  appiEmoji: {
    fontSize: 16,
    lineHeight: 20,
  },
  profile: {
    width: 22,
    height: 22,
    alignItems: 'center',
    gap: 2,
  },
  profileHead: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  profileBody: {
    width: 18,
    height: 9,
    borderRadius: 9,
    borderWidth: 2,
    borderBottomWidth: 0,
  },
});

export function CustomTabBar({ activeScreen, onTabPress }: CustomTabBarProps) {
  const insets = useSafeAreaInsets();

  const tabs: { key: TabScreen; label: string; Icon: React.ComponentType<{ color: string }> }[] = [
    { key: 'home', label: 'Главная', Icon: HomeIcon },
    { key: 'catalog', label: 'Каталог', Icon: CatalogIcon },
    { key: 'cart', label: 'Корзина', Icon: CartIcon },
    { key: 'appi', label: 'Аппи', Icon: AppiIcon },
    { key: 'profile', label: 'Профиль', Icon: ProfileIcon },
  ];

  return (
    <View style={[styles.container, { paddingBottom: insets.bottom }]}>
      {tabs.map(tab => {
        const active = tab.key === activeScreen;
        const color = active ? GREEN_ACTIVE : INACTIVE;
        return (
          <TouchableOpacity
            key={tab.key}
            style={styles.tab}
            onPress={() => onTabPress(tab.key)}
            activeOpacity={0.7}>
            <tab.Icon color={color} />
            <Text style={[styles.tabLabel, { color }]}>{tab.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.07)',
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingTop: 10,
    paddingBottom: 6,
    gap: 3,
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: '500',
  },
});
