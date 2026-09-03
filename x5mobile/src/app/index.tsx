import { StyleSheet, Text, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';

export default function HomeScreen() {
  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.header}>
          <Text style={styles.emoji}>😊</Text>
          <ThemedText type="title" style={styles.title}>
            Добро пожаловать в X5 Лояльность
          </ThemedText>
        </View>

        <View style={styles.statsCard}>
          <ThemedText style={styles.statsLabel}>Вы сэкономили</ThemedText>
          <ThemedText style={styles.statsValue}>2,450 ₽</ThemedText>
          <ThemedText style={styles.statsSubtitle}>в этом месяце</ThemedText>
        </View>

        <View style={styles.levelCard}>
          <ThemedText style={styles.levelTitle}>Ваш уровень</ThemedText>
          <View style={styles.levelBadge}>
            <Text style={styles.levelNumber}>5</Text>
          </View>
          <ThemedText style={styles.levelProgress}>Ещё 1,200 ₽ до уровня 6</ThemedText>
        </View>

        <Pressable style={styles.button} onPress={() => {}}>
          <ThemedText style={styles.buttonText}>Начать</ThemedText>
        </Pressable>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
  },
  safeArea: {
    flex: 1,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 32,
  },
  header: {
    alignItems: 'center',
    gap: 16,
  },
  emoji: {
    fontSize: 72,
  },
  title: {
    textAlign: 'center',
    fontSize: 24,
    fontWeight: '600',
  },
  statsCard: {
    alignItems: 'center',
    padding: 24,
    borderRadius: 16,
    backgroundColor: '#f5f5f5',
    width: '100%',
    gap: 8,
  },
  statsLabel: {
    fontSize: 14,
    opacity: 0.7,
  },
  statsValue: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#2ecc71',
  },
  statsSubtitle: {
    fontSize: 12,
    opacity: 0.6,
  },
  levelCard: {
    alignItems: 'center',
    padding: 20,
    borderRadius: 12,
    backgroundColor: '#f0f0f0',
    width: '100%',
    gap: 12,
  },
  levelTitle: {
    fontSize: 14,
    opacity: 0.7,
  },
  levelBadge: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  levelNumber: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#fff',
  },
  levelProgress: {
    fontSize: 12,
    opacity: 0.6,
  },
  button: {
    backgroundColor: '#007AFF',
    paddingHorizontal: 48,
    paddingVertical: 16,
    borderRadius: 10,
    width: '100%',
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
