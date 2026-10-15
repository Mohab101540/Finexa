import { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';

import { Card, Chip, LABEL, Screen, SectionTitle, Txt } from '@/components/finexa-ui';
import { ReviewBadge } from '@/components/identify-payment';
import { C, F } from '@/constants/theme';
import { Analysis, money, PastedSms, Review, useDemo } from '@/demo-data';

type Tried = { key: number; sms: Omit<PastedSms, 'id'>; result: Analysis; addedAs?: string };

export default function TrySmsScreen() {
  const { offline, history, analyze, added, addSms, clearAdded } = useDemo();
  const [body, setBody] = useState('');
  const [sender, setSender] = useState('');
  const [date, setDate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [tried, setTried] = useState<Tried[]>([]); // this session's SMS, newest first; tried[0] is the latest result
  const [showResult, setShowResult] = useState(false);

  const onAnalyze = () => {
    const sms = { body: body.trim(), sender: sender.trim(), date: date.trim() };
    setBusy(true);
    setError('');
    analyze(sms)
      .then((result) => {
        setTried((t) => [{ key: Date.now(), sms, result }, ...t]);
        setShowResult(true);
      })
      .catch((e) => setError(`Could not analyze: ${e.message}`))
      .finally(() => setBusy(false));
  };

  const onAdd = (item: Tried) => {
    const id = `added-${item.key}`;
    addSms({ id, ...item.sms });
    setTried((t) => t.map((x) => (x.key === item.key ? { ...x, addedAs: id } : x)));
  };

  const onReview = (key: number, review: Review) =>
    setTried((t) => t.map((x) => (x.key === key ? { ...x, result: { ...x.result, review } } : x)));

  const onRemoveAdded = () => {
    clearAdded();
    setTried((t) => t.map((x) => ({ ...x, addedAs: undefined })));
  };

  const onClear = () => {
    setBody('');
    setSender('');
    setDate('');
    setError('');
    setShowResult(false);
  };

  const shown = showResult ? tried[0] : null;
  const canAnalyze = !offline && !busy && body.trim().length > 0;

  return (
    <Screen title="Try SMS" intro="Paste any SMS and watch Finexa read it, sort it, and explain every step.">
      <Card style={{ gap: 12 }}>
        <TextInput
          value={body}
          onChangeText={setBody}
          multiline
          maxLength={1000}
          placeholder="الصق رسالة SMS هنا…"
          placeholderTextColor={C.faint}
          accessibilityLabel="SMS text"
          style={[s.input, s.smsInput]}
        />
        <View style={s.row}>
          <TextInput
            value={sender}
            onChangeText={setSender}
            maxLength={50}
            placeholder="Sender (optional)"
            placeholderTextColor={C.faint}
            accessibilityLabel="Sender"
            style={[s.input, { flex: 1 }]}
          />
          <TextInput
            value={date}
            onChangeText={setDate}
            maxLength={10}
            placeholder={history?.today ?? 'YYYY-MM-DD'}
            placeholderTextColor={C.faint}
            accessibilityLabel="Date, YYYY-MM-DD, empty means today"
            style={[s.input, { flex: 1 }]}
          />
        </View>
        <Txt style={s.hint}>Date as YYYY-MM-DD. Empty = today in the demo ({history?.today ?? '…'}).</Txt>
        <View style={s.row}>
          <Pressable
            accessibilityRole="button"
            disabled={!canAnalyze}
            onPress={onAnalyze}
            style={({ pressed }) => [s.primary, !canAnalyze && s.disabled, pressed && { opacity: 0.85 }]}>
            <Txt style={s.primaryText}>{busy ? 'Analyzing…' : 'Analyze'}</Txt>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={onClear}
            style={({ pressed }) => [s.secondary, pressed && { opacity: 0.85 }]}>
            <Txt style={s.secondaryText}>Clear</Txt>
          </Pressable>
        </View>
        {offline && <Txt style={s.hint}>Analyzing needs a connection to Finexa.</Txt>}
        {!!error && <Txt style={[s.hint, { color: C.red }]}>{error}</Txt>}
      </Card>

      {shown && <Result tried={shown} onAdd={onAdd} onReview={onReview} />}

      {added.length > 0 && (
        <Pressable accessibilityRole="button" onPress={onRemoveAdded}>
          <Txt style={[s.hint, s.link]}>
            Remove the {added.length} added SMS from my messages
          </Txt>
        </Pressable>
      )}

      {tried.length > 0 && (
        <>
          <SectionTitle>Analyzed this session</SectionTitle>
          {tried.map((t) => (
            <Card key={t.key} style={{ gap: 6 }}>
              <View style={s.row}>
                <Chip label={LABEL[t.result.label].text} color={LABEL[t.result.label].color} />
                <Txt style={s.hint}>{t.addedAs ? 'Added' : 'Not added'}</Txt>
              </View>
              <Txt style={s.arabic} numberOfLines={2}>
                {t.result.body}
              </Txt>
              <Txt style={s.hint}>
                {t.result.sender} · EGP {money(t.result.effect.before)} → {money(t.result.effect.after)}
              </Txt>
            </Card>
          ))}
        </>
      )}
    </Screen>
  );
}

function Result({
  tried,
  onAdd,
  onReview,
}: {
  tried: Tried;
  onAdd: (item: Tried) => void;
  onReview: (key: number, review: Review) => void;
}) {
  const r = tried.result;
  const diff = r.effect.difference;
  const field = (name: string, value: string) => (
    <View style={s.field}>
      <Txt style={s.fieldName}>{name}</Txt>
      <Txt style={s.fieldValue}>{value}</Txt>
    </View>
  );
  return (
    <>
      <Card style={{ gap: 10 }}>
        <View style={s.row}>
          <Txt style={s.cardTitle}>What Finexa found</Txt>
          <Chip label={LABEL[r.label].text} color={LABEL[r.label].color} />
        </View>
        {r.review && <ReviewBadge review={r.review} onChanged={(review) => onReview(tried.key, review)} />}
        {field(
          'AI model',
          `${LABEL[r.ml.label].text} · ${Math.round(r.ml.confidence * 100)}% sure` +
            (r.ml.label === 'needs_review' ? ` (best guess: ${LABEL[r.ml.best_guess].text})` : ''),
        )}
        {field('Amount', r.amount === null ? 'Not found' : `EGP ${money(r.amount)}`)}
        {field('Direction', r.direction === 'in' ? 'Money in' : r.direction === 'out' ? 'Money out' : 'Unknown')}
        {field('Sender', r.sender)}
        {field('Date', r.date.slice(0, 10))}
      </Card>

      <SectionTitle>Why</SectionTitle>
      {r.why.map((w, i) => (
        <View key={i} style={s.why}>
          <Txt style={s.whyText}>{w}</Txt>
        </View>
      ))}

      <SectionTitle>Effect on your limit</SectionTitle>
      <Card style={{ gap: 8 }}>
        <Txt style={s.effect}>
          EGP {money(r.effect.before)} → {money(r.effect.after)}{' '}
          <Txt style={{ color: diff > 0 ? C.green : diff < 0 ? C.red : C.faint }}>
            ({diff > 0 ? '+' : diff < 0 ? '−' : '±'}EGP {money(Math.abs(diff))})
          </Txt>
        </Txt>
        {r.effect.changes.length ? (
          r.effect.changes.map((c) => (
            <Txt key={c} style={s.hint}>
              • {c}
            </Txt>
          ))
        ) : (
          <Txt style={s.hint}>Nothing in the calculation changes.</Txt>
        )}
        <Pressable
          accessibilityRole="button"
          disabled={!!tried.addedAs}
          onPress={() => onAdd(tried)}
          style={({ pressed }) => [s.primary, !!tried.addedAs && s.disabled, pressed && { opacity: 0.85 }]}>
          <Txt style={s.primaryText}>{tried.addedAs ? 'Added to my messages' : 'Add to my messages'}</Txt>
        </Pressable>
        {tried.addedAs && <Txt style={[s.hint, { color: C.green }]}>Home and Inbox now include this SMS.</Txt>}
      </Card>
    </>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 },
  input: {
    backgroundColor: C.bg,
    borderColor: C.line,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: C.text,
    fontFamily: F.regular,
    fontSize: 14,
  },
  smsInput: { minHeight: 120, fontFamily: F.arabic, fontSize: 15, textAlign: 'right', writingDirection: 'rtl', textAlignVertical: 'top' },
  hint: { color: C.muted, fontSize: 13 },
  link: { color: C.amber, textDecorationLine: 'underline', textAlign: 'center' },
  primary: { flex: 1, backgroundColor: C.indigo, borderRadius: 16, paddingVertical: 14, alignItems: 'center' },
  disabled: { backgroundColor: C.line },
  primaryText: { fontFamily: F.bold, fontSize: 15 },
  secondary: { borderColor: C.line, borderWidth: 1, borderRadius: 16, paddingVertical: 14, paddingHorizontal: 22, alignItems: 'center' },
  secondaryText: { color: C.muted, fontFamily: F.semibold, fontSize: 15 },
  cardTitle: { fontFamily: F.semibold, fontSize: 16 },
  field: { flexDirection: 'row', justifyContent: 'space-between' },
  fieldName: { color: C.muted, fontSize: 14 },
  fieldValue: { fontFamily: F.semibold, fontSize: 14, fontVariant: ['tabular-nums'] },
  why: { backgroundColor: C.surface, borderRadius: 12, borderLeftWidth: 3, borderLeftColor: C.indigo, paddingVertical: 10, paddingHorizontal: 14 },
  whyText: { fontSize: 14, lineHeight: 22 },
  effect: { fontFamily: F.bold, fontSize: 20, lineHeight: 28, fontVariant: ['tabular-nums'] },
  arabic: { fontFamily: F.arabic, fontSize: 14, lineHeight: 22, color: '#E4E4E7', textAlign: 'right', writingDirection: 'rtl' },
});
