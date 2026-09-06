import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Keyboard,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { EconomyCard, PersonalChallenges } from '@/components/screens/personal-sections';
import type { BasketState } from '@/hooks/useBasket';
import { useVibes, type Vibe } from '@/hooks/useVibes';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';

interface AppiViewProps {
  token: string;
  basket: BasketState;
  onOpenBasket: () => void;
  onChallenges: () => void;
}

function vibeEmoji(vibe: Vibe): string {
  const value = `${vibe.name} ${vibe.description}`.toLowerCase();
  if (value.includes('здоров') || value.includes('пп')) return '🥗';
  if (value.includes('готов') || value.includes('быстр')) return '🍱';
  if (value.includes('коф')) return '☕';
  if (value.includes('сем')) return '🛍️';
  if (value.includes('эконом')) return '🛒';
  if (value.includes('необыч') || value.includes('нов')) return '🍝';
  return '🍽️';
}

function MicrophoneIcon() {
  return (
    <View style={styles.microphone}>
      <View style={styles.microphoneCapsule} />
      <View style={styles.microphoneStem} />
      <View style={styles.microphoneBase} />
    </View>
  );
}

export function AppiView({
  token,
  basket,
  onOpenBasket,
  onChallenges,
}: AppiViewProps) {
  const insets = useSafeAreaInsets();
  const { vibes, selectedVibeId, loading, saving, error, saveVibe } = useVibes(token);
  const [draftVibeId, setDraftVibeId] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    setDraftVibeId(selectedVibeId);
  }, [selectedVibeId]);

  async function submitBasketRequest(text = query) {
    const request = text.trim();
    if (!request || basket.loading || !basket.hydrated) return;
    Keyboard.dismiss();
    const applied = await basket.sendInstruction(request);
    if (applied) {
      setQuery('');
      onOpenBasket();
    }
  }

  async function saveSelection() {
    await saveVibe(draftVibeId);
  }

  const draftVibe = vibes.find(vibe => vibe.id === draftVibeId);

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 12 }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <View style={styles.heroCopy}>
            <Text style={styles.title}>Аппи</Text>
            <Text style={styles.subtitle}>Ваш помощник в покупках</Text>
          </View>
          <Image
            source={require('../../../assets/images/mascot.png')}
            style={styles.mascot}
            resizeMode="contain"
          />
        </View>

        <View style={styles.search}>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Что собрать для вас?"
            placeholderTextColor="#8B8F8B"
            style={styles.input}
            returnKeyType="send"
            editable={!basket.loading}
            onSubmitEditing={() => submitBasketRequest()}
          />
          {basket.loading ? (
            <ActivityIndicator color={GREEN} size="small" />
          ) : (
            <TouchableOpacity
              style={[styles.searchAction, !query.trim() && styles.searchActionInactive]}
              onPress={() => submitBasketRequest()}
              activeOpacity={0.75}
              disabled={!query.trim()}>
              {query.trim()
                ? <Text style={[styles.searchActionText, styles.searchActionTextActive]}>→</Text>
                : <MicrophoneIcon />}
            </TouchableOpacity>
          )}
        </View>
        {basket.message ? <Text style={styles.basketMessage}>{basket.message}</Text> : null}

        <View style={styles.vibeSection}>
          <Text style={styles.sectionTitle}>Вайб месяца</Text>
          <Text style={styles.sectionSubtitle}>Выберите направление</Text>
          <Text style={styles.vibeDescription}>
            Аппи учтёт ваш выбор и историю покупок,{'\n'}
            чтобы предложить подходящие задания.
          </Text>

          {loading ? (
            <ActivityIndicator color={GREEN} style={styles.loader} />
          ) : (
            <View style={styles.vibeGrid}>
              {vibes.length === 0 && (
                <Text style={styles.emptyVibes}>Направления пока не добавлены</Text>
              )}
              {vibes.map(vibe => {
                const selected = draftVibeId === vibe.id;
                return (
                  <TouchableOpacity
                    key={vibe.id}
                    style={[styles.vibeCard, selected && styles.vibeCardSelected]}
                    onPress={() => setDraftVibeId(selected ? null : vibe.id)}
                    activeOpacity={0.78}>
                    <Text style={styles.vibeEmoji}>{vibeEmoji(vibe)}</Text>
                    <Text style={styles.vibeName} numberOfLines={2}>{vibe.name}</Text>
                    <View style={[styles.radio, selected && styles.radioSelected]}>
                      {selected && <View style={styles.radioDot} />}
                    </View>
                  </TouchableOpacity>
                );
              })}
            </View>
          )}

          {draftVibe?.llm_context ? (
            <Text style={styles.vibeContext}>Для Аппи: {draftVibe.llm_context}</Text>
          ) : null}

          <Text style={styles.changeHint}>Можно изменить позже</Text>
          {error ? <Text style={styles.inlineError}>Не удалось загрузить или сохранить выбор</Text> : null}
          <TouchableOpacity
            style={[styles.saveButton, (saving || loading) && styles.saveButtonDisabled]}
            onPress={saveSelection}
            disabled={saving || loading}
            activeOpacity={0.82}>
            {saving
              ? <ActivityIndicator color="#FFFFFF" />
              : <Text style={styles.saveButtonText}>Сохранить выбор</Text>}
          </TouchableOpacity>
        </View>

        <PersonalChallenges token={token} onDetails={onChallenges} />

        <View style={styles.economySection}>
          <Text style={styles.sectionTitle}>Экономия с Аппи</Text>
          <EconomyCard token={token} onChallenges={onChallenges} />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 25, paddingBottom: 28, gap: 20 },
  hero: {
    height: 65,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  heroCopy: { paddingTop: 2 },
  title: { color: DARK_GREEN, fontSize: 31, lineHeight: 34, fontWeight: '900' },
  subtitle: { color: MUTED, fontSize: 13, marginTop: 3 },
  mascot: { width: 106, height: 96, marginTop: -16, marginRight: -8 },

  search: {
    height: 56,
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 14,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    backgroundColor: '#FFFFFF',
  },
  input: { flex: 1, color: TEXT, fontSize: 14, paddingVertical: 0 },
  searchAction: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: GREEN,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchActionInactive: { backgroundColor: 'transparent' },
  searchActionText: { color: GREEN, fontSize: 22, fontWeight: '700' },
  searchActionTextActive: { color: '#FFFFFF' },
  microphone: { width: 20, height: 24, alignItems: 'center' },
  microphoneCapsule: {
    width: 9,
    height: 14,
    borderRadius: 5,
    borderWidth: 2,
    borderColor: GREEN,
  },
  microphoneStem: { width: 2, height: 5, backgroundColor: GREEN },
  microphoneBase: { width: 10, height: 2, borderRadius: 1, backgroundColor: GREEN },
  basketMessage: { color: MUTED, fontSize: 11, textAlign: 'center', marginTop: -12 },
  inlineError: { color: '#C74335', fontSize: 11, textAlign: 'center', marginTop: -12 },

  vibeSection: { gap: 5 },
  sectionTitle: { color: DARK_GREEN, fontSize: 20, fontWeight: '900' },
  sectionSubtitle: { color: MUTED, fontSize: 13 },
  vibeDescription: { color: '#646964', fontSize: 12, lineHeight: 17, marginTop: 7, marginBottom: 8 },
  loader: { marginVertical: 48 },
  vibeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  emptyVibes: { color: MUTED, fontSize: 13, paddingVertical: 24, width: '100%', textAlign: 'center' },
  vibeCard: {
    width: '48.5%',
    minHeight: 76,
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 14,
    paddingHorizontal: 9,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#FFFFFF',
  },
  vibeCardSelected: { borderColor: GREEN, backgroundColor: '#F7FCF8' },
  vibeEmoji: { fontSize: 31 },
  vibeName: { flex: 1, color: TEXT, fontSize: 12, lineHeight: 15, fontWeight: '700' },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: '#C7CBC7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { borderColor: GREEN },
  radioDot: { width: 12, height: 12, borderRadius: 6, backgroundColor: GREEN },
  vibeContext: { color: '#646964', fontSize: 12, lineHeight: 17, marginTop: 4 },
  changeHint: { color: GREEN, fontSize: 12, marginTop: 5 },
  saveButton: {
    height: 50,
    borderRadius: 13,
    backgroundColor: GREEN,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 9,
  },
  saveButtonDisabled: { opacity: 0.6 },
  saveButtonText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },

  economySection: { gap: 10 },
});
