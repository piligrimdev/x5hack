import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { User } from '@/mock-data';

interface HomeViewProps {
  user: User;
  goSavings: () => void;
  goHistory: () => void;
}

function LocationIcon() {
  return (
    <View style={styles.locationIconWrapper}>
      <Text style={styles.locationIconText}>📍</Text>
    </View>
  );
}

function BellIcon() {
  return <Text style={styles.headerIconText}>🔔</Text>;
}

function QuestionIcon() {
  return <Text style={styles.headerIconText}>?</Text>;
}

function QrPlaceholder() {
  return (
    <View style={styles.qrContainer}>
      {Array.from({ length: 5 }).map((_, row) =>
        Array.from({ length: 5 }).map((__, col) => (
          <View
            key={`${row}-${col}`}
            style={[
              styles.qrCell,
              { backgroundColor: (row + col) % 2 === 0 ? 'rgba(255,255,255,0.18)' : 'rgba(255,255,255,0.07)' },
            ]}
          />
        ))
      )}
      <View style={styles.qrLabel}>
        <Text style={styles.qrLabelText}>QR код</Text>
      </View>
    </View>
  );
}

export function HomeView({ user, goSavings, goHistory }: HomeViewProps) {
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.root}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <TouchableOpacity style={styles.locationPill} activeOpacity={0.7}>
          <LocationIcon />
          <Text style={styles.locationText}>Укажите адрес</Text>
        </TouchableOpacity>
        <View style={styles.headerActions}>
          <TouchableOpacity style={styles.headerIconBtn} activeOpacity={0.7}>
            <BellIcon />
          </TouchableOpacity>
          <TouchableOpacity style={styles.headerIconBtn} activeOpacity={0.7}>
            <QuestionIcon />
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}>

        {/* Loyalty Card */}
        <View style={styles.loyaltyCard}>
          <QrPlaceholder />
          <View style={styles.cardInfo}>
            <View style={styles.cardTitleRow}>
              <Text style={styles.cardTitleText}>Бонусная карта</Text>
              <View style={styles.levelBadge}>
                <Text style={styles.levelBadgeText}>{user.level}</Text>
              </View>
            </View>
            <Text style={styles.pointsText}>{user.points} баллов</Text>
            <View style={styles.pillRow}>
              <View style={styles.cashbackPill}>
                <Text style={styles.cashbackPillText}>Кешбэк {user.cashback}</Text>
              </View>
              <View style={styles.categoryPill}>
                <Text style={styles.categoryPillText}>Категории {user.categoryBonus}</Text>
              </View>
            </View>
          </View>
        </View>

        {/* Quick Actions */}
        <View style={styles.quickActions}>
          <QuickActionBtn
            iconBg="#EAF7EE"
            iconColor="#1E9E5A"
            iconChar="Э"
            label={'Экономия\nи задания'}
            onPress={goSavings}
          />
          <QuickActionBtn
            iconBg="#F1EFE9"
            iconColor="#8A6B2E"
            iconChar="И"
            label={'История\nпокупок'}
            onPress={goHistory}
          />
          <QuickActionBtn
            iconBg="#F3EAF0"
            iconColor="#B23B7A"
            iconChar="О"
            label={'Оценка\nтоваров'}
            onPress={() => {}}
          />
          <QuickActionBtn
            iconBg="#EAEEF6"
            iconColor="#3A5BA0"
            iconChar="%"
            label="Кешбэк"
            onPress={() => {}}
          />
        </View>
      </ScrollView>
    </View>
  );
}

interface QuickActionBtnProps {
  iconBg: string;
  iconColor: string;
  iconChar: string;
  label: string;
  onPress: () => void;
}

function QuickActionBtn({ iconBg, iconColor, iconChar, label, onPress }: QuickActionBtnProps) {
  return (
    <TouchableOpacity style={styles.quickBtn} activeOpacity={0.7} onPress={onPress}>
      <View style={[styles.quickBtnIcon, { backgroundColor: iconBg }]}>
        <Text style={[styles.quickBtnIconChar, { color: iconColor }]}>{iconChar}</Text>
      </View>
      <Text style={styles.quickBtnLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: BrandColors.appBg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 14,
    backgroundColor: BrandColors.appBg,
  },
  locationPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    borderRadius: 100,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.08)',
    paddingVertical: 9,
    paddingHorizontal: 14,
    gap: 6,
  },
  locationIconWrapper: {
    width: 16,
    height: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  locationIconText: {
    fontSize: 12,
  },
  locationText: {
    fontSize: 13.5,
    fontWeight: '600',
    color: BrandColors.textPrimary,
  },
  headerActions: {
    flexDirection: 'row',
    gap: 8,
  },
  headerIconBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerIconText: {
    fontSize: 15,
    color: BrandColors.textPrimary,
    fontWeight: '700',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    gap: 20,
  },
  loyaltyCard: {
    backgroundColor: BrandColors.dark,
    borderRadius: 18,
    padding: 18,
    flexDirection: 'row',
    gap: 14,
  },
  qrContainer: {
    width: 76,
    height: 76,
    borderRadius: 10,
    overflow: 'hidden',
    flexDirection: 'row',
    flexWrap: 'wrap',
    position: 'relative',
  },
  qrCell: {
    width: '20%',
    height: '20%',
  },
  qrLabel: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  qrLabelText: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 10,
    fontWeight: '600',
  },
  cardInfo: {
    flex: 1,
    gap: 8,
  },
  cardTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  cardTitleText: {
    color: BrandColors.textSecondary,
    fontSize: 13,
    fontWeight: '600',
  },
  levelBadge: {
    backgroundColor: BrandColors.goldLight,
    borderRadius: 100,
    paddingVertical: 3,
    paddingHorizontal: 8,
  },
  levelBadgeText: {
    color: BrandColors.dark,
    fontSize: 10.5,
    fontWeight: '700',
  },
  pointsText: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  pillRow: {
    flexDirection: 'row',
    gap: 6,
    flexWrap: 'wrap',
  },
  cashbackPill: {
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderRadius: 100,
    paddingVertical: 4,
    paddingHorizontal: 10,
  },
  cashbackPillText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  categoryPill: {
    backgroundColor: BrandColors.red,
    borderRadius: 100,
    paddingVertical: 4,
    paddingHorizontal: 10,
  },
  categoryPillText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  quickActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  quickBtn: {
    alignItems: 'center',
    gap: 8,
    flex: 1,
  },
  quickBtnIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  quickBtnIconChar: {
    fontSize: 20,
    fontWeight: '700',
  },
  quickBtnLabel: {
    fontSize: 11,
    color: BrandColors.textPrimary,
    textAlign: 'center',
    lineHeight: 14,
  },
});
