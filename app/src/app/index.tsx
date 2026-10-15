import Slider from '@react-native-community/slider';
import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Card, Loading, ReasonCard, Screen, SectionTitle, Txt } from '@/components/finexa-ui';
import { C, F } from '@/constants/theme';
import { BAND_COLOR, DemoUser, Method, Mode, money, useDemo } from '@/demo-data';

const STEP = 50; // withdraw in EGP 50 steps
type Option<T> = { value: T; label: string; note: string };
const METHODS: Option<Method>[] = [
  { value: 'bank', label: 'Bank account', note: 'Repaid automatically on payday' },
  { value: 'wallet', label: 'Mobile wallet', note: 'You approve each repayment (−5%)' },
];
const MODES: Option<Mode>[] = [
  { value: 'rules', label: 'Rules', note: 'Your tier sets the rate' },
  { value: 'ai', label: 'AI model', note: 'Salary model sets the rate' },
];
const USERS: Option<DemoUser>[] = [
  { value: 'main', label: 'Main', note: 'Demo user' },
  { value: 'high', label: 'High', note: '90th pct' },
  { value: 'medium', label: 'Medium', note: '50th pct' },
  { value: 'low', label: 'Low', note: '15th pct' },
  { value: 'job_loss', label: 'Lost job', note: 'Overdue' },
];

function Segment<T extends string>({
  options,
  value,
  onChange,
  compact = false, // smaller padding and text, for 5 options in one row
}: {
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
  compact?: boolean;
}) {
  return (
    <View style={s.segment} accessibilityRole="radiogroup">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: on }}
            onPress={() => onChange(o.value)}
            style={[s.segmentItem, compact && s.segmentCompact, on && s.segmentOn]}>
            <Txt style={[s.segmentLabel, compact && { fontSize: 13 }, !on && { color: C.faint }]}>{o.label}</Txt>
            <Txt style={s.segmentNote}>{o.note}</Txt>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function HomeScreen() {
  const { demo, offline, withTalabat, setWithTalabat, method, setMethod, mode, setMode, user, setUser, withdraw } =
    useDemo();
  const max = demo ? Math.floor(demo.available / STEP) * STEP : 0;
  const [amount, setAmount] = useState(0);
  const [sent, setSent] = useState<string | null>(null);

  useEffect(() => setAmount((a) => (a > 0 && a <= max ? a : Math.floor(max / 2 / STEP) * STEP)), [max]);

  const onWithdraw = () => {
    withdraw(amount);
    setSent(`EGP ${money(amount, 0)} sent to your ${method === 'bank' ? 'bank account' : 'mobile wallet'}.`);
  };

  return (
    <Screen title="Finexa">
      <View style={s.balance}>
        <LinearGradient
          colors={['#0F0E14', '#2E3F6A', '#72274A']}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 0 }}
          style={StyleSheet.absoluteFill}
        />
        <LinearGradient colors={['transparent', '#0F172A']} locations={[0, 0.9]} style={StyleSheet.absoluteFill} />
        <Txt style={s.balanceLabel}>Available to withdraw now</Txt>
        {demo ? (
          <>
            <View style={s.amountRow}>
              <Txt style={s.amount}>{money(demo.available)}</Txt>
              <Txt style={s.currency}>EGP</Txt>
            </View>
            {demo.tier && (
              <View style={s.balanceFooter}>
                <View>
                  <Txt style={s.footLabel}>Earned so far</Txt>
                  <Txt style={s.footValue}>EGP {money(demo.calc.earned)}</Txt>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Txt style={s.footLabel}>{demo.ai ? 'Tier · AI rate' : 'Tier'}</Txt>
                  <Txt style={s.footValue}>
                    {demo.tier} · {demo.calc.rate}%
                  </Txt>
                </View>
              </View>
            )}
          </>
        ) : (
          <Loading />
        )}
      </View>

      {!!demo?.to_review && (
        <Pressable accessibilityRole="link" onPress={() => router.push('/inbox')} style={s.review}>
          <Txt style={s.reviewText}>
            {demo.to_review} {demo.to_review === 1 ? 'payment' : 'payments'} to review
          </Txt>
          <Txt style={s.reviewText}>›</Txt>
        </Pressable>
      )}

      {demo && (
        <Pressable accessibilityRole="link" onPress={() => router.push('/outlook')} style={s.health}>
          <View>
            <Txt style={s.healthLabel}>Financial health</Txt>
            <Txt style={[s.healthBand, { color: BAND_COLOR[demo.health.band] }]}>{demo.health.band}</Txt>
          </View>
          <Txt style={s.healthScore}>
            {demo.health.score}
            <Txt style={s.healthOf}> / 100 ›</Txt>
          </Txt>
        </Pressable>
      )}

      <SectionTitle>Demo user</SectionTitle>
      <Segment options={USERS} value={user} onChange={setUser} compact />
      {demo && demo.user.key !== 'main' && (
        <Txt style={s.hint}>
          {demo.user.title}: simulated test user {demo.user.source_user} (never seen by the model in training), HR
          salary EGP {money(demo.user.hr_salary, 0)}. An illustrative example; the model is evaluated on all test
          users. Home only: Inbox and History show the main user.
        </Txt>
      )}
      <SectionTitle>Decision mode</SectionTitle>
      <Segment options={MODES} value={mode} onChange={setMode} />
      <Segment options={METHODS} value={method} onChange={setMethod} />

      <Card style={{ gap: 12 }}>
        <View style={s.row}>
          <Txt style={s.sliderLabel}>Amount</Txt>
          <Txt style={s.sliderValue}>EGP {money(amount, 0)}</Txt>
        </View>
        {max >= STEP && !offline ? (
          <Slider
            style={{ width: '100%', height: 40 }}
            value={amount}
            minimumValue={0}
            maximumValue={max}
            step={STEP}
            onValueChange={(v) => setAmount(Math.round(v))}
            minimumTrackTintColor={C.indigo}
            maximumTrackTintColor={C.line}
            thumbTintColor="#FFFFFF"
            accessibilityLabel="Amount to withdraw"
          />
        ) : (
          <Txt style={s.hint}>
            {offline ? 'Withdrawing needs a connection to Finexa.' : 'Nothing to withdraw right now.'}
          </Txt>
        )}
        <Pressable
          accessibilityRole="button"
          disabled={offline || amount < STEP || !demo}
          onPress={onWithdraw}
          style={({ pressed }) => [s.primary, (offline || amount < STEP) && s.disabled, pressed && { opacity: 0.85 }]}>
          <Txt style={s.primaryText}>Withdraw EGP {money(amount, 0)}</Txt>
        </Pressable>
        {sent && <Txt style={[s.hint, { color: C.green }]}>{sent}</Txt>}
      </Card>

      {demo && (
        <>
          <SectionTitle>Why this amount</SectionTitle>
          {demo.ai?.paragraph && (
            <Card style={{ ...s.aiCard, ...(demo.ai.needs_review && { borderColor: C.amber + '66' }) }}>
              <View style={s.row}>
                <Txt style={s.aiTitle}>AI model</Txt>
                <Txt style={[s.aiBadge, demo.ai.needs_review && { color: C.amber }]}>
                  {demo.ai.needs_review ? 'Needs review' : `${Math.round(demo.ai.p * 100)}% on time`}
                </Txt>
              </View>
              <Txt style={s.aiText}>{demo.ai.paragraph}</Txt>
              {demo.ai.notes.map((n, i) => (
                <Txt key={i} style={s.aiNote}>
                  Data note: {n}
                </Txt>
              ))}
            </Card>
          )}
          {demo.reasons.map((r, i) => (
            <ReasonCard key={i} reason={r} />
          ))}
          {demo.what_if && (
            <>
              <SectionTitle>How to unlock more</SectionTitle>
              <ReasonCard reason={demo.what_if} highlight />
            </>
          )}
        </>
      )}

      <Pressable
        accessibilityRole="button"
        disabled={!demo}
        onPress={() => setWithTalabat(!withTalabat)}
        style={({ pressed }) => [s.secondary, pressed && { opacity: 0.85 }]}>
        <Txt style={s.secondaryText}>{withTalabat ? 'Remove the Talabat SMS' : 'Simulate a Talabat payout SMS'}</Txt>
      </Pressable>
    </Screen>
  );
}

const s = StyleSheet.create({
  balance: {
    borderRadius: 28,
    padding: 22,
    borderWidth: 1,
    borderColor: C.indigo + '4D',
    backgroundColor: '#0F172A',
    overflow: 'hidden', // keeps the gradient inside the rounded corners
    shadowColor: C.indigo,
    shadowOpacity: 0.3,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 20 },
    elevation: 10,
  },
  balanceLabel: { color: '#C7D2FE', fontFamily: F.medium, fontSize: 13 },
  amountRow: { flexDirection: 'row', alignItems: 'baseline', gap: 6, marginTop: 6 },
  amount: { fontFamily: F.bold, fontSize: 46, lineHeight: 56, letterSpacing: -1.5, fontVariant: ['tabular-nums'] },
  currency: { fontFamily: F.semibold, fontSize: 20, color: '#C7D2FE' },
  balanceFooter: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 24 },
  footLabel: { color: '#A5B4FC', fontSize: 12, lineHeight: 16 },
  footValue: { fontFamily: F.semibold, fontSize: 14, fontVariant: ['tabular-nums'] },
  review: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderColor: C.amber + '66',
    borderWidth: 1,
    borderRadius: 14,
    paddingVertical: 10,
    paddingHorizontal: 14,
    backgroundColor: C.amber + '14',
  },
  reviewText: { color: C.amber, fontFamily: F.semibold, fontSize: 14 },
  health: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: C.surface,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 16,
    paddingVertical: 12,
    paddingHorizontal: 16,
  },
  healthLabel: { color: C.muted, fontSize: 13 },
  healthBand: { fontFamily: F.semibold, fontSize: 16 },
  healthScore: { fontFamily: F.bold, fontSize: 28, fontVariant: ['tabular-nums'] },
  healthOf: { color: C.faint, fontFamily: F.medium, fontSize: 14 },
  segment: { flexDirection: 'row', backgroundColor: C.bg, borderColor: C.line, borderWidth: 1, borderRadius: 16, padding: 4 },
  segmentItem: { flex: 1, borderRadius: 12, paddingVertical: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: 'transparent' },
  segmentCompact: { paddingHorizontal: 4, alignItems: 'center' },
  segmentOn: { backgroundColor: C.surface, borderColor: '#3F3F46' },
  segmentLabel: { fontFamily: F.semibold, fontSize: 14 },
  segmentNote: { color: C.faint, fontSize: 11, lineHeight: 15 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  sliderLabel: { color: C.muted, fontFamily: F.medium, fontSize: 14 },
  sliderValue: { color: '#A5B4FC', fontFamily: F.bold, fontSize: 20, fontVariant: ['tabular-nums'] },
  hint: { color: C.muted, fontSize: 13 },
  aiCard: { gap: 8, borderColor: C.indigo + '66' },
  aiTitle: { fontFamily: F.semibold, fontSize: 15 },
  aiBadge: { color: '#A5B4FC', fontFamily: F.semibold, fontSize: 13 },
  aiText: { fontSize: 14, lineHeight: 21 },
  aiNote: { color: C.faint, fontSize: 12, lineHeight: 17 },
  primary: { backgroundColor: C.indigo, borderRadius: 16, paddingVertical: 15, alignItems: 'center' },
  disabled: { backgroundColor: C.line },
  primaryText: { fontFamily: F.bold, fontSize: 15 },
  secondary: { borderColor: C.amber + '66', borderWidth: 1, borderRadius: 16, paddingVertical: 14, alignItems: 'center', marginTop: 8 },
  secondaryText: { color: C.amber, fontFamily: F.semibold, fontSize: 15 },
});
