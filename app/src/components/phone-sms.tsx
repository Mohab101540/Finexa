import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { Card, Chip, LABEL, Txt } from '@/components/finexa-ui';
import { C, F } from '@/constants/theme';
import { get, money, shortDate, Sms } from '@/demo-data';
import { readPhoneSms } from '@/phone-sms';

const SHOWN = 15;

export function PhoneSmsCard() {
  const [rows, setRows] = useState<Sms[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onRead() {
    setBusy(true);
    setError(null);
    try {
      const messages = await readPhoneSms();
      const body = JSON.stringify({ messages });
      setRows(await get<Sms[]>('/classify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body }));
    } catch (e) {
      setRows(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const counts = rows?.reduce<Record<string, number>>((n, m) => ({ ...n, [m.label]: (n[m.label] ?? 0) + 1 }), {});

  return (
    <Card style={{ gap: 10 }}>
      <Txt style={s.title}>Your phone's real SMS</Txt>
      <Txt style={s.hint}>
        Reads the latest messages on this phone after you allow it, and sorts them like the sample ones. They are sent to
        the Finexa backend to be sorted and are not saved there.
      </Txt>
      <Pressable
        accessibilityRole="button"
        disabled={busy}
        onPress={onRead}
        style={({ pressed }) => [s.primary, busy && { opacity: 0.6 }, pressed && { opacity: 0.85 }]}>
        {busy ? <ActivityIndicator color="#fff" /> : <Txt style={s.primaryText}>Read my phone's SMS</Txt>}
      </Pressable>
      {error && <Txt style={[s.hint, { color: C.red }]}>{error}</Txt>}
      {rows && counts && (
        <>
          <Txt style={s.hint}>Found {rows.length} messages.</Txt>
          <View style={s.chips}>
            {(Object.keys(LABEL) as Sms['label'][]).map((k) => (
              <Chip key={k} label={`${LABEL[k].text} ${counts[k] ?? 0}`} color={LABEL[k].color} />
            ))}
          </View>
          {rows.slice(0, SHOWN).map((m) => (
            <View key={m.id} style={s.item}>
              <View style={s.row}>
                <Txt style={s.sender}>{m.sender}</Txt>
                <Txt style={s.date}>{shortDate(m.date)}</Txt>
              </View>
              <Txt style={s.body} numberOfLines={3}>
                {m.body}
              </Txt>
              <View style={s.row}>
                <Chip label={LABEL[m.label].text} color={LABEL[m.label].color} />
                {m.amount !== null && m.direction && (
                  <Txt style={[s.amount, { color: m.direction === 'in' ? C.green : C.muted }]}>
                    {m.direction === 'in' ? '+' : '−'}EGP {money(m.amount)}
                  </Txt>
                )}
              </View>
            </View>
          ))}
          {rows.length > SHOWN && <Txt style={s.hint}>…and {rows.length - SHOWN} more.</Txt>}
        </>
      )}
    </Card>
  );
}

const s = StyleSheet.create({
  title: { fontFamily: F.semibold, fontSize: 16 },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19 },
  primary: { backgroundColor: C.indigo, borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  primaryText: { color: '#fff', fontFamily: F.semibold, fontSize: 15 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  item: { gap: 6, borderTopWidth: 1, borderTopColor: C.line, paddingTop: 10 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  sender: { fontFamily: F.semibold, fontSize: 14 },
  date: { color: C.faint, fontSize: 12 },
  body: { fontFamily: F.arabic, fontSize: 14, lineHeight: 24, color: '#E4E4E7', textAlign: 'right', writingDirection: 'rtl' },
  amount: { fontFamily: F.semibold, fontSize: 14, fontVariant: ['tabular-nums'] },
});
