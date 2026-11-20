import { ReactNode, useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Pressable, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Txt } from '@/components/finexa-ui';
import { errorText, useAuth } from '@/auth';
import { C, F } from '@/constants/theme';

type Tab = 'login' | 'signup';

function Field({ label, note, children }: { label: string; note?: string; children: ReactNode }) {
  return (
    <View style={{ gap: 6 }}>
      <Txt style={s.label}>{label}</Txt>
      {children}
      {note && <Txt style={s.note}>{note}</Txt>}
    </View>
  );
}

function Choice<T extends string>({ options, value, onChange }: { options: [T, string][]; value: T; onChange: (v: T) => void }) {
  return (
    <View style={s.segment} accessibilityRole="radiogroup">
      {options.map(([v, label]) => (
        <Pressable
          key={v}
          accessibilityRole="radio"
          accessibilityState={{ checked: v === value }}
          onPress={() => onChange(v)}
          style={[s.segmentItem, v === value && s.segmentOn]}>
          <Txt style={[s.segmentText, v !== value && { color: C.faint }]}>{label}</Txt>
        </Pressable>
      ))}
    </View>
  );
}

export function AuthScreen() {
  const { login, signup, exploreDemo } = useAuth();
  const [tab, setTab] = useState<Tab>('login');
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [salary, setSalary] = useState('');
  const [employer, setEmployer] = useState('');
  const [method, setMethod] = useState<'bank' | 'wallet'>('bank');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    setBusy(true);
    setError(null);
    try {
      const cleanPhone = phone.replace(/\s/g, '');
      if (tab === 'login') await login(cleanPhone, password);
      else
        await signup({
          name,
          phone: cleanPhone,
          password,
          hr_salary: salary.trim() ? Number(salary.replace(/,/g, '')) : null,
          employer: employer.trim() || null,
          method,
        });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView behavior="height" style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
          <View style={{ gap: 6, marginBottom: 8 }}>
            <Txt style={s.logo} accessibilityRole="header">
              Finexa
            </Txt>
            <Txt style={s.tagline}>Get part of the salary you have already earned, before payday.</Txt>
          </View>

          <Choice<Tab>
            options={[
              ['login', 'Log in'],
              ['signup', 'Sign up'],
            ]}
            value={tab}
            onChange={(t) => {
              setTab(t);
              setError(null);
            }}
          />

          {tab === 'signup' && (
            <Field label="Full name">
              <TextInput style={s.input} value={name} onChangeText={setName} autoComplete="name" placeholderTextColor={C.faint} />
            </Field>
          )}
          <Field label="Mobile number">
            <TextInput
              style={s.input}
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              autoComplete="tel"
              maxLength={13}
              placeholder="01012345678"
              placeholderTextColor={C.faint}
            />
          </Field>
          <Field label="Password" note={tab === 'signup' ? 'At least 8 characters.' : undefined}>
            <TextInput
              style={s.input}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              autoComplete={tab === 'signup' ? 'new-password' : 'current-password'}
              placeholderTextColor={C.faint}
            />
          </Field>

          {tab === 'signup' && (
            <>
              <Field label="Monthly net salary (EGP)" note="As on your HR letter. Finexa checks it against your salary SMS.">
                <TextInput style={s.input} value={salary} onChangeText={setSalary} keyboardType="numeric" placeholder="15000" placeholderTextColor={C.faint} />
              </Field>
              <Field label="Employer" note="Optional. Lets Finexa spot your salary from the first payment.">
                <TextInput style={s.input} value={employer} onChangeText={setEmployer} placeholderTextColor={C.faint} />
              </Field>
              <Field label="Where your salary arrives">
                <Choice
                  options={[
                    ['bank', 'Bank account'],
                    ['wallet', 'Mobile wallet'],
                  ]}
                  value={method}
                  onChange={setMethod}
                />
              </Field>
            </>
          )}

          {error && <Txt style={s.error}>{error}</Txt>}

          <Pressable
            accessibilityRole="button"
            disabled={busy}
            onPress={onSubmit}
            style={({ pressed }) => [s.primary, busy && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}>
            {busy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Txt style={s.primaryText}>{tab === 'login' ? 'Log in' : 'Create account'}</Txt>
            )}
          </Pressable>

          <Pressable accessibilityRole="button" onPress={exploreDemo} style={s.demo}>
            <Txt style={s.demoText}>Explore the demo without an account ›</Txt>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  content: { padding: 20, paddingTop: 48, gap: 16 },
  logo: { fontFamily: F.bold, fontSize: 34, letterSpacing: -1 },
  tagline: { color: C.muted, fontSize: 15, lineHeight: 22 },
  label: { color: C.muted, fontFamily: F.medium, fontSize: 13 },
  note: { color: C.faint, fontSize: 12, lineHeight: 17 },
  input: {
    backgroundColor: C.surface,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: C.text,
    fontFamily: F.regular,
    fontSize: 16,
  },
  segment: { flexDirection: 'row', backgroundColor: C.bg, borderColor: C.line, borderWidth: 1, borderRadius: 14, padding: 4 },
  segmentItem: { flex: 1, borderRadius: 10, paddingVertical: 10, alignItems: 'center', borderWidth: 1, borderColor: 'transparent' },
  segmentOn: { backgroundColor: C.surface, borderColor: '#3F3F46' },
  segmentText: { fontFamily: F.semibold, fontSize: 14 },
  error: { color: C.red, fontSize: 14, lineHeight: 20 },
  primary: { backgroundColor: C.indigo, borderRadius: 16, paddingVertical: 15, alignItems: 'center', marginTop: 4 },
  primaryText: { fontFamily: F.bold, fontSize: 15 },
  demo: { alignItems: 'center', paddingVertical: 12 },
  demoText: { color: '#A5B4FC', fontFamily: F.semibold, fontSize: 14 },
});
