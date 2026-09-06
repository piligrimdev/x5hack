import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ApiError, apiLogin, apiRegister } from '@/api/client';

const GREEN = '#138F3E';
const DARK_GREEN = '#164E2B';
const TEXT = '#17211A';
const MUTED = '#7E827F';
const BORDER = '#E5E8E5';
const PHONE_GROUPS = [3, 3, 2, 2] as const;
const PHONE_LENGTH = 10;
const CODE_LENGTH = 6;

function onlyDigits(value: string): string {
  return value.replace(/\D/g, '');
}

function sanitizeChars(value: string, charset: 'digits' | 'latin'): string {
  if (charset === 'digits') return onlyDigits(value);
  return value.replace(/[^A-Za-z0-9]/g, '');
}

function nationalDigits(raw: string): string {
  let digits = onlyDigits(raw);
  if (digits.length > PHONE_LENGTH && (digits.startsWith('7') || digits.startsWith('8'))) {
    digits = digits.slice(1);
  }
  return digits.slice(0, PHONE_LENGTH);
}

function splitGroups(digits: string, sizes: readonly number[]): string[] {
  const parts: string[] = [];
  let cursor = 0;
  for (const size of sizes) {
    parts.push(digits.slice(cursor, cursor + size));
    cursor += size;
  }
  return parts;
}

function loginHint(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404 || error.status === 403) {
      return 'Этот номер ещё не зарегистрирован. Нажмите «Зарегистрироваться».';
    }
    if (error.status === 422) {
      return 'Проверьте номер телефона и попробуйте ещё раз.';
    }
    return 'Не удалось войти. Попробуйте ещё раз — или зарегистрируйтесь, если аккаунта нет.';
  }
  return 'Нет соединения с сервером. Проверьте сеть и попробуйте ещё раз.';
}

function registerHint(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return 'Этот номер уже есть. Нажмите «Войти».';
    }
    if (error.status === 422) {
      return 'Проверьте номер телефона и попробуйте ещё раз.';
    }
    return 'Не удалось зарегистрироваться. Попробуйте ещё раз или войдите, если аккаунт уже есть.';
  }
  return 'Нет соединения с сервером. Проверьте сеть и попробуйте ещё раз.';
}

function SegmentedDigits({
  groups,
  value,
  onChange,
  autoFocus,
  charset = 'digits',
}: {
  groups: readonly number[];
  value: string;
  onChange: (digits: string) => void;
  autoFocus?: boolean;
  charset?: 'digits' | 'latin';
}) {
  const refs = useRef<Array<TextInput | null>>([]);
  const parts = splitGroups(value, groups);
  const total = groups.reduce((sum, size) => sum + size, 0);
  const isPhone = charset === 'digits';

  function focusGroup(index: number) {
    refs.current[Math.max(0, Math.min(index, groups.length - 1))]?.focus();
  }

  function handleChange(index: number, text: string) {
    const incoming = sanitizeChars(text, charset);
    const beforeLen = groups.slice(0, index).reduce((sum, size) => sum + size, 0);

    if (incoming.length > groups[index]) {
      const next = value.slice(0, beforeLen) + incoming;
      onChange(next);
      const filled = Math.min(next.length, total);
      let cursor = 0;
      let nextIndex = groups.length - 1;
      for (let i = 0; i < groups.length; i += 1) {
        cursor += groups[i];
        if (filled < cursor) {
          nextIndex = i;
          break;
        }
        if (filled === cursor) {
          nextIndex = Math.min(i + 1, groups.length - 1);
          break;
        }
      }
      focusGroup(nextIndex);
      return;
    }

    const nextParts = [...parts];
    nextParts[index] = incoming;
    onChange(nextParts.join('').slice(0, total));
    if (incoming.length >= groups[index]) {
      focusGroup(index + 1);
    }
  }

  function handleKeyPress(index: number, key: string) {
    if (key === 'Backspace' && parts[index].length === 0 && index > 0) {
      const nextParts = [...parts];
      nextParts[index - 1] = nextParts[index - 1].slice(0, -1);
      onChange(nextParts.join(''));
      focusGroup(index - 1);
    }
  }

  return (
    <View style={styles.segments}>
      {groups.map((size, index) => (
        <TextInput
          key={`${size}-${index}`}
          ref={(node) => {
            refs.current[index] = node;
          }}
          style={[styles.segment, { flex: size }]}
          value={parts[index]}
          onChangeText={(text) => handleChange(index, text)}
          onKeyPress={({ nativeEvent }) => handleKeyPress(index, nativeEvent.key)}
          keyboardType={isPhone ? 'number-pad' : Platform.OS === 'ios' ? 'ascii-capable' : 'visible-password'}
          autoCapitalize="none"
          autoCorrect={false}
          maxLength={size + 8}
          textContentType={isPhone && index === 0 ? 'telephoneNumber' : 'none'}
          autoComplete={isPhone && index === 0 ? 'tel' : 'off'}
          autoFocus={autoFocus && index === 0}
          selectTextOnFocus
        />
      ))}
    </View>
  );
}

interface LoginViewProps {
  onLogin: (token: string) => void;
}

export function LoginView({ onLogin }: LoginViewProps) {
  const insets = useSafeAreaInsets();
  const [phoneDigits, setPhoneDigits] = useState('');
  const [referralCode, setReferralCode] = useState('');
  const [draftCode, setDraftCode] = useState('');
  const [referralOpen, setReferralOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [hintTone, setHintTone] = useState<'error' | 'ok'>('error');

  useEffect(() => {
    if (referralOpen) setDraftCode(referralCode);
  }, [referralOpen, referralCode]);

  const phone = `+7${phoneDigits}`;
  const phoneReady = phoneDigits.length === PHONE_LENGTH;

  function requirePhone(): boolean {
    if (phoneReady) return true;
    setHintTone('error');
    setHint('Введите номер полностью: +7 и 10 цифр.');
    return false;
  }

  async function handleLogin() {
    if (!requirePhone()) return;
    setLoading(true);
    setHint(null);
    try {
      const token = await apiLogin(phone, referralCode || undefined);
      onLogin(token);
    } catch (error: unknown) {
      setHintTone('error');
      setHint(loginHint(error));
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister() {
    if (!requirePhone()) return;
    setLoading(true);
    setHint(null);
    try {
      const token = await apiRegister(phone, referralCode || undefined);
      onLogin(token);
    } catch (error: unknown) {
      setHintTone('error');
      setHint(registerHint(error));
    } finally {
      setLoading(false);
    }
  }

  function saveReferral() {
    if (draftCode.length !== CODE_LENGTH) {
      return;
    }
    setReferralCode(draftCode);
    setReferralOpen(false);
    setHintTone('ok');
    setHint(`Реферальный код ${draftCode} сохранится до входа или регистрации.`);
  }

  function clearReferral() {
    setReferralCode('');
    setDraftCode('');
    setReferralOpen(false);
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[styles.content, { paddingTop: insets.top + 36, paddingBottom: insets.bottom + 24 }]}>
        <Text style={styles.eyebrow}>Вход</Text>
        <Text style={styles.title}>Добро пожаловать</Text>
        <Text style={styles.subtitle}>
          Введите номер телефона, чтобы войти или создать аккаунт
        </Text>

        <Text style={styles.fieldLabel}>Номер телефона</Text>
        <View style={styles.phoneRow}>
          <View style={styles.prefix}>
            <Text style={styles.prefixText}>+7</Text>
          </View>
          <View style={styles.phoneGroups}>
            <SegmentedDigits
              groups={PHONE_GROUPS}
              value={phoneDigits}
              onChange={(digits) => setPhoneDigits(nationalDigits(digits))}
            />
          </View>
        </View>

        {hint ? (
          <Text style={hintTone === 'ok' ? styles.hintOk : styles.hintError}>{hint}</Text>
        ) : null}

        <TouchableOpacity
          style={[styles.loginBtn, (loading || !phoneReady) && styles.btnDisabled]}
          onPress={handleLogin}
          activeOpacity={0.8}
          disabled={loading}>
          {loading
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.loginBtnText}>Войти</Text>}
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.registerBtn, loading && styles.btnDisabled]}
          onPress={handleRegister}
          activeOpacity={0.8}
          disabled={loading}>
          <Text style={styles.registerBtnText}>Зарегистрироваться</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.referralLink}
          onPress={() => setReferralOpen(true)}
          activeOpacity={0.7}
          disabled={loading}>
          <Text style={styles.referralLinkText}>
            {referralCode ? `Код ${referralCode} сохранён` : 'У меня есть реферальный код'}
          </Text>
        </TouchableOpacity>
      </View>

      <Modal
        visible={referralOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setReferralOpen(false)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setReferralOpen(false)}>
          <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
            <Pressable style={[styles.modalCard, { paddingBottom: insets.bottom + 18 }]} onPress={() => {}}>
              <Text style={styles.modalTitle}>Реферальный код</Text>
              <Text style={styles.modalSubtitle}>
                6 символов: латинские буквы любого регистра или цифры. Код сохранится и уйдёт вместе со входом или регистрацией.
              </Text>
              <SegmentedDigits
                groups={[1, 1, 1, 1, 1, 1]}
                value={draftCode}
                onChange={(digits) => setDraftCode(sanitizeChars(digits, 'latin').slice(0, CODE_LENGTH))}
                charset="latin"
                autoFocus
              />
              <TouchableOpacity
                style={[styles.loginBtn, draftCode.length !== CODE_LENGTH && styles.btnDisabled]}
                onPress={saveReferral}
                activeOpacity={0.8}
                disabled={draftCode.length !== CODE_LENGTH}>
                <Text style={styles.loginBtnText}>Сохранить код</Text>
              </TouchableOpacity>
              {referralCode ? (
                <TouchableOpacity style={styles.clearBtn} onPress={clearReferral} activeOpacity={0.7}>
                  <Text style={styles.clearBtnText}>Удалить код</Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity style={styles.clearBtn} onPress={() => setReferralOpen(false)} activeOpacity={0.7}>
                  <Text style={styles.clearBtnText}>Отмена</Text>
                </TouchableOpacity>
              )}
            </Pressable>
          </KeyboardAvoidingView>
        </Pressable>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#FFFFFF' },
  content: { flex: 1, paddingHorizontal: 22, gap: 12 },
  eyebrow: { color: GREEN, fontSize: 13, fontWeight: '800', letterSpacing: 0.4 },
  title: { color: DARK_GREEN, fontSize: 28, fontWeight: '900' },
  subtitle: { color: MUTED, fontSize: 15, lineHeight: 21, marginBottom: 10 },
  fieldLabel: { color: TEXT, fontSize: 13, fontWeight: '700' },
  phoneRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  prefix: {
    minWidth: 54,
    height: 56,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: '#F7F8F6',
    alignItems: 'center',
    justifyContent: 'center',
  },
  prefixText: { color: TEXT, fontSize: 18, fontWeight: '800' },
  phoneGroups: { flex: 1 },
  segments: { flexDirection: 'row', gap: 6 },
  segment: {
    height: 56,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: '#FFFFFF',
    textAlign: 'center',
    fontSize: 18,
    fontWeight: '800',
    color: TEXT,
  },
  hintError: { color: '#C74335', fontSize: 13, lineHeight: 18 },
  hintOk: { color: GREEN, fontSize: 13, lineHeight: 18 },
  loginBtn: {
    backgroundColor: GREEN,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 8,
  },
  loginBtnText: { color: '#fff', fontSize: 16, fontWeight: '800' },
  registerBtn: {
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: GREEN,
    paddingVertical: 15,
    alignItems: 'center',
  },
  registerBtnText: { color: GREEN, fontSize: 16, fontWeight: '800' },
  btnDisabled: { opacity: 0.45 },
  referralLink: { alignItems: 'center', paddingVertical: 8 },
  referralLinkText: { color: DARK_GREEN, fontSize: 14, fontWeight: '700' },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(23,23,26,0.45)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    paddingHorizontal: 18,
    paddingTop: 18,
    gap: 12,
  },
  modalTitle: { color: DARK_GREEN, fontSize: 20, fontWeight: '900' },
  modalSubtitle: { color: MUTED, fontSize: 13, lineHeight: 18 },
  clearBtn: { alignItems: 'center', paddingVertical: 8 },
  clearBtnText: { color: MUTED, fontSize: 14, fontWeight: '700' },
});
