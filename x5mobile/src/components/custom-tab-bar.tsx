import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';

export type TabScreen = 'home' | 'savings' | 'history';

interface CustomTabBarProps {
  activeScreen: TabScreen;
  onTabPress: (tab: 'home' | 'catalog' | 'bonus' | 'profile') => void;
}

const ACTIVE = BrandColors.red;
const INACTIVE = '#B4B3AF';

// SVG-иконки через View-примитивы (без react-native-svg)

function HomeIcon({ color }: { color: string }) {
  return (
    <View style={[tabIconStyles.house]}>
      {/* Крыша */}
      <View style={[tabIconStyles.roof, { borderBottomColor: color }]} />
      {/* Стены + дверь */}
      <View style={[tabIconStyles.walls, { backgroundColor: color }]}>
        <View style={[tabIconStyles.door, { backgroundColor: INACTIVE === color ? '#F6F4F1' : '#fff' }]} />
      </View>
    </View>
  );
}

function CatalogIcon({ color }: { color: string }) {
  return (
    <View style={tabIconStyles.grid}>
      <View style={tabIconStyles.gridRow}>
        <View style={[tabIconStyles.gridCell, { backgroundColor: color }]} />
        <View style={[tabIconStyles.gridCell, { backgroundColor: color }]} />
      </View>
      <View style={tabIconStyles.gridRow}>
        <View style={[tabIconStyles.gridCell, { backgroundColor: color }]} />
        <View style={[tabIconStyles.gridCell, { backgroundColor: color }]} />
      </View>
    </View>
  );
}

function BonusIcon({ color }: { color: string }) {
  // Пятиконечная звезда через символ ★
  return <Text style={[tabIconStyles.starText, { color }]}>★</Text>;
}

function ProfileIcon({ color }: { color: string }) {
  return (
    <View style={tabIconStyles.profile}>
      <View style={[tabIconStyles.profileHead, { backgroundColor: color }]} />
      <View style={[tabIconStyles.profileBody, { borderColor: color }]} />
    </View>
  );
}

const tabIconStyles = StyleSheet.create({
  house: {
    width: 22,
    height: 20,
    alignItems: 'center',
  },
  roof: {
    width: 0,
    height: 0,
    borderLeftWidth: 11,
    borderRightWidth: 11,
    borderBottomWidth: 9,
    borderLeftColor: 'transparent',
    borderRightColor: 'transparent',
  },
  walls: {
    width: 16,
    height: 11,
    borderRadius: 1,
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingBottom: 0,
  },
  door: {
    width: 5,
    height: 7,
    borderRadius: 2,
    marginBottom: 0,
  },
  grid: {
    width: 20,
    height: 20,
    gap: 3,
  },
  gridRow: {
    flex: 1,
    flexDirection: 'row',
    gap: 3,
  },
  gridCell: {
    flex: 1,
    borderRadius: 3,
  },
  starText: {
    fontSize: 22,
    lineHeight: 22,
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

  // "Главная" всегда активна — все три экрана (home/savings/history) принадлежат ей
  const tabs = [
    { key: 'home' as const, label: 'Главная', Icon: HomeIcon, active: true },
    { key: 'catalog' as const, label: 'Каталог', Icon: CatalogIcon, active: false },
    { key: 'bonus' as const, label: 'Бонусы', Icon: BonusIcon, active: false },
    { key: 'profile' as const, label: 'Профиль', Icon: ProfileIcon, active: false },
  ];

  return (
    <View style={[styles.container, { paddingBottom: insets.bottom }]}>
      {tabs.map(tab => {
        const color = tab.active ? ACTIVE : INACTIVE;
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
