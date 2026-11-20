import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { errorText, useAuth } from '@/auth';
import { Card, ReasonCard, Txt } from '@/components/finexa-ui';
import { type Progress, STATUS_TEXT } from '@/components/onboarding';
import { C, F } from '@/constants/theme';
import { get, money, Reason } from '@/demo-data';
import { readPhoneSms } from '@/phone-sms';

type Limit = { available: number; max_withdrawal: number; tier: string; reasons: Reason[]; attendance: { status: string } };
type Me = { tier: string; on_time_streak: number };

const post = (body: object): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export function AccountCard() {
  const { account, logout, setOnboarding } = useAuth();
  const [me, setMe] = useState<Me | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [messages, setMessages] = useState<object[] | null>(null); // the phone's SMS, read once per check
  const [limit, setLimit] = useState<Limit | null>(null);
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    get<Me>('/me').then(setMe).catch(() => setMe(null));
    get<Progress>('/onboarding').then(setProgress).catch(() => setProgress(null));
  }, []);

  const verify = () =>
    run(async () => {
      setProgress(await get<Progress>('/onboarding/verify', post({})));
    });

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const check = () =>
    run(async () => {
      const sms = await readPhoneSms();
      setMessages(sms);
      setLimit(await get<Limit>('/limit', post({ messages: sms })));
      setDone(null);
    });

  const withdraw = () =>
    run(async () => {
      const res = await get<{ withdrawn: number; fee: number; total_owed: number }>(
        '/withdraw',
        post({ messages, amount: Number(amount) }),
      );
      setDone(`Recorded EGP ${money(res.withdrawn)} + fee EGP ${money(res.fee, 0)} = EGP ${money(res.total_owed)} owed on payday.`);
      setAmount('');
      setLimit(await get<Limit>('/limit', post({ messages })));
      setMe(await get<Me>('/me'));
    });

  if (!account) return null;
  return (
    <Card style={{ gap: 10, borderColor: C.indigo + '66' }}>
      <View style={s.row}>
        <View style={{ flex: 1 }}>
          <Txt style={s.title}>{account.name}</Txt>
          <Txt style={s.hint}>
            {account.phone} · {me ? `${me.tier}, ${me.on_time_streak} on time in a row` : 'Starter'}
          </Txt>
        </View>
        <Pressable accessibilityRole="button" onPress={logout} style={s.logout}>
          <Txt style={s.logoutText}>Log out</Txt>
        </Pressable>
      </View>

      {progress && (
        <View style={[s.row, s.verify]}>
          <View style={{ flex: 1 }}>
            <Txt style={[s.verifyLabel, { color: STATUS_TEXT[progress.status].color }]}>{STATUS_TEXT[progress.status].label}</Txt>
            <Txt style={s.note}>
              {progress.status === 'incomplete'
                ? `${progress.missing.length} sign-up ${progress.missing.length === 1 ? 'step' : 'steps'} left`
                : progress.face?.reason ?? 'ID, selfie, work and HR letter sent'}
            </Txt>
          </View>
          {progress.status === 'incomplete' ? (
            <Pressable accessibilityRole="button" onPress={() => setOnboarding(true)} style={s.logout}>
              <Txt style={s.logoutText}>Finish</Txt>
            </Pressable>
          ) : progress.status === 'needs_review' ? (
            <Pressable accessibilityRole="button" disabled={busy} onPress={verify} style={s.logout}>
              <Txt style={s.logoutText}>Approve (demo)</Txt>
            </Pressable>
          ) : null}
        </View>
      )}

      {limit ? (
        <>
          <Txt style={s.label}>Your real limit, from this phone's SMS</Txt>
          <Txt style={s.amount}>EGP {money(limit.available)}</Txt>
          <Txt style={s.hint}>Most you can withdraw now, after the fee: EGP {money(limit.max_withdrawal)}</Txt>
          {limit.reasons.slice(0, 4).map((r, i) => (
            <ReasonCard key={i} reason={r} />
          ))}
          {limit.max_withdrawal > 0 && (
            <View style={s.row}>
              <TextInput
                style={s.input}
                value={amount}
                onChangeText={setAmount}
                keyboardType="numeric"
                placeholder="Amount in EGP"
                placeholderTextColor={C.faint}
              />
              <Pressable
                accessibilityRole="button"
                disabled={busy || !(Number(amount) > 0)}
                onPress={withdraw}
                style={[s.primary, !(Number(amount) > 0) && { backgroundColor: C.line }]}>
                <Txt style={s.primaryText}>Withdraw</Txt>
              </Pressable>
            </View>
          )}
          {done && <Txt style={[s.hint, { color: C.green }]}>{done}</Txt>}
        </>
      ) : (
        <Txt style={s.hint}>
          Reads this phone's SMS (with your permission) and works out how much you can withdraw. New accounts start at
          Starter with a personal cap of EGP 1,000.
        </Txt>
      )}

      <Pressable accessibilityRole="button" disabled={busy} onPress={check} style={s.secondary}>
        {busy ? <ActivityIndicator color={C.text} /> : <Txt style={s.secondaryText}>{limit ? 'Check again' : 'Check my limit'}</Txt>}
      </Pressable>
      {error && <Txt style={[s.hint, { color: C.red }]}>{error}</Txt>}
      <Txt style={s.note}>The demo below is the fictional demo user, not your account.</Txt>
    </Card>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  title: { fontFamily: F.semibold, fontSize: 17 },
  label: { color: C.muted, fontFamily: F.medium, fontSize: 13, marginTop: 4 },
  amount: { fontFamily: F.bold, fontSize: 30, fontVariant: ['tabular-nums'] },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19 },
  note: { color: C.faint, fontSize: 12 },
  verify: { borderTopColor: C.line, borderTopWidth: 1, paddingTop: 10 },
  verifyLabel: { fontFamily: F.semibold, fontSize: 14 },
  logout: { borderColor: C.line, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 6 },
  logoutText: { color: C.muted, fontFamily: F.semibold, fontSize: 13 },
  input: {
    flex: 1,
    backgroundColor: C.bg,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: C.text,
    fontFamily: F.regular,
    fontSize: 15,
  },
  primary: { backgroundColor: C.indigo, borderRadius: 12, paddingVertical: 11, paddingHorizontal: 18 },
  primaryText: { fontFamily: F.bold, fontSize: 14 },
  secondary: { borderColor: C.indigo + '88', borderWidth: 1, borderRadius: 12, paddingVertical: 11, alignItems: 'center' },
  secondaryText: { color: '#A5B4FC', fontFamily: F.semibold, fontSize: 14 },
});
