import { useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { errorText } from '@/auth';
import { Card, Txt } from '@/components/finexa-ui';
import { C, F } from '@/constants/theme';
import { API_URL, get } from '@/demo-data';

type Forwarded = { count: number; messages: { date: string; sender: string; amount: number; direction: string }[] };

const STEPS = [
  'Open the Shortcuts app → Automation → New Automation → Message.',
  'Sender: your bank or wallet (for example CIB, NBE, Vodafone Cash, InstaPay). Message contains: جنيه or EGP.',
  'Choose "Run Immediately", then add the action "Get Contents of URL".',
  'URL: the address below. Method: POST. Header: X-Finexa-Key = your key.',
  'Request body JSON: "body" = the message content, "sender" = the message sender.',
];

export function IphoneForwardingCard() {
  const [key, setKey] = useState<string | null>(null);
  const [forwarded, setForwarded] = useState<Forwarded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const url = `${API_URL}/sms/forward`;

  const load = () => get<Forwarded>('/sms/forwarded').then(setForwarded).catch(() => {});
  useEffect(() => {
    load();
  }, []);

  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const makeKey = () =>
    run(async () => {
      const res = await get<{ key: string }>('/sms/forward-key', { method: 'POST' });
      setKey(res.key);
    });

  const deleteAll = () =>
    run(async () => {
      await get('/sms/forwarded', { method: 'DELETE' });
      await load();
    });

  return (
    <Card style={{ gap: 10 }}>
      <Txt style={s.title}>iPhone: forward your bank SMS</Txt>
      <Txt style={s.muted}>
        {Platform.OS === 'ios'
          ? 'iPhones don\'t let apps read SMS. A Shortcuts automation can send just your bank and wallet messages to Finexa.'
          : 'For iPhone users. Android reads your SMS directly, so you don\'t need this. Shown here for testing.'}
      </Txt>
      {STEPS.map((step, i) => (
        <Txt key={i} style={s.step}>
          {i + 1}. {step}
        </Txt>
      ))}
      <Txt style={s.code} selectable>
        {url}
      </Txt>
      {key && (
        <Txt style={s.code} selectable>
          X-Finexa-Key: {key}
        </Txt>
      )}
      <Pressable accessibilityRole="button" onPress={makeKey} style={s.button}>
        <Txt style={s.buttonText}>{key ? 'Make a new key (the old one stops)' : 'Make my forwarding key'}</Txt>
      </Pressable>
      {key && <Txt style={s.muted}>Long-press the key to copy it. It is shown only once. It can only send SMS, not log in.</Txt>}
      {forwarded && (
        <View style={s.row}>
          <Txt style={s.muted}>
            {forwarded.count} money SMS received. OTPs and ads are dropped on arrival; texts are deleted after 120 days.
          </Txt>
          {forwarded.count > 0 && (
            <Pressable accessibilityRole="button" onPress={deleteAll}>
              <Txt style={[s.muted, { color: C.red }]}>Delete all</Txt>
            </Pressable>
          )}
        </View>
      )}
      {error && <Txt style={[s.muted, { color: C.red }]}>{error}</Txt>}
    </Card>
  );
}

const s = StyleSheet.create({
  title: { fontFamily: F.semibold, fontSize: 16 },
  step: { fontSize: 13, lineHeight: 19 },
  code: { fontFamily: F.medium, fontSize: 12, borderColor: C.line, borderWidth: 1, borderRadius: 8, padding: 8 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  button: { borderColor: C.line, borderWidth: 1, borderRadius: 12, paddingVertical: 12, alignItems: 'center', minHeight: 46 },
  buttonText: { fontFamily: F.semibold, fontSize: 14 },
  muted: { color: C.muted, fontSize: 13, lineHeight: 19, flexShrink: 1 },
});
